""" Add location information to photos in Apple Photos which lack this from Google location history """


import json
import os
import pathlib
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Optional

import click
from osxphotos import ExifTool, ExportResults, PhotoInfo, PhotosDB
from osxphotos.photosalbum import PhotosAlbum
from photoscript import PhotosLibrary

DEFAULT_TIME_DELTA = 60
LOCATION_HISTORY = None

__version__ = "0.01"


def msec_to_datetime(msec: int, utc: bool = False):
    """Convert milliseconds to datetime object
    Args:
        msec: int, timestamp in milliseconds
        utc: bool; if True, adds UTC timezone, otherwise returns naive object
    """

    tz = timezone.utc if utc else None
    return datetime.fromtimestamp(msec / 1000, tz=tz)


class LocationHistory:
    """Location history from Google Takeout 'Location History.json'"""

    def __init__(self, filename: str):
        self.filename = filename
        self.location_history = self._load_location_history(filename)
        self.timestamps = self._extract_timestamps_from_history()
        self.location_dict = self._location_history_to_dict_by_timestamp()

    def nearest_location(self, timestamp: datetime):
        """Return tuple of (nearest location record, delta in sec) to given timestamp"""
        msec = int(timestamp.timestamp() * 1000)
        nearest = self._nearest_location_from_timestamp(msec)
        nearest_record = self.location_dict[nearest]
        return nearest_record, abs(int(nearest_record["timestampMs"]) - msec) / 1000

    def _load_location_history(self, filename: str) -> list:
        """Load location history from Google Takeout JSON file

        Args:
            filename: path to JSON file

        Returns:
            list of location records
        """

        with open(filename, "r") as f:
            location_data = json.load(f)
            try:
                location_history = location_data["locations"]
                for location in location_history:
                    location["datetime"] = msec_to_datetime(
                        int(location["timestampMs"]), utc=True
                    )
                    location["latitude"] = (
                        location["latitudeE7"] / 1e7
                        if "latitudeE7" in location
                        else None
                    )
                    location["longitude"] = (
                        location["longitudeE7"] / 1e7
                        if "longitudeE7" in location
                        else None
                    )
                return sorted(location_history, key=lambda x: x["timestampMs"])
            except KeyError:
                raise ValueError("Location history not found in JSON file")

    def _extract_timestamps_from_history(self) -> list:
        """Given list of location history records, returns list of timestamps as ints"""
        return [int(x["timestampMs"]) for x in self.location_history]

    def _nearest_location_from_timestamp(self, timestamp: int):
        """Given a timestamp in msec, find nearest (in time) location record"""
        i = bisect_left(self.timestamps, timestamp)
        return min(
            self.timestamps[max(0, i - 1) : i + 2],
            key=lambda t: abs(timestamp - t),
        )

    def _location_history_to_dict_by_timestamp(self) -> dict:
        """Convert location history to dict by timestamp"""
        return {int(x["timestampMs"]): x for x in self.location_history}

    def __len__(self):
        return len(self.location_history)


def add_location_to_photo(
    photo: PhotoInfo,
    location_history,
    delta: int,
    dry_run: bool,
    album: Optional[PhotosAlbum] = None,
) -> int:
    """Add location information to photo record, returns 1 if location added, else 0"""
    nearest_location, nearest_delta = location_history.nearest_location(photo.date)
    nearest_delta = int(nearest_delta)
    if nearest_delta >= delta:
        return 0

    click.echo(
        f"Found location match for {photo.original_filename} taken on {photo.date} within {nearest_delta} seconds: {nearest_location['latitude']}, {nearest_location['longitude']}"
    )
    if not dry_run:
        try:
            photolib = PhotosLibrary()
            library_photo = photolib.photos(uuid=[photo.uuid])
            if library_photo:
                library_photo = list(library_photo)[0]
            else:
                click.echo(f"Error: could not access photo for uuid {photo.uuid}")
                return 0
            library_photo.location = (
                nearest_location["latitude"],
                nearest_location["longitude"],
            )
            click.echo(f"Added location to photo")
            if album:
                album.add(photo)
        except Exception as e:
            click.echo(f"Error: could not add location to photo {e}")
            return 0
    return 1


def add_location_to_photo_osxphotos(
    photo: PhotoInfo, results: ExportResults, verbose: callable, **kwargs
):
    """Given a Google Takeout location history specified by env OSXPHOTOS_LOCATION_HISTORY, add missing location data to photo

    This function for use with osxphotos and --post-function option as in:

    OSXPHOTOS_LOCATION_HISTORY="Location History.json" osxphotos export /path/to/export --post-function add_photo_locations_from_google_history.py::add_location_to_photo_osxphotos

    Requires exiftool to be installed and available on the PATH
    """

    global LOCATION_HISTORY

    history_file = os.environ.get("OSXPHOTOS_LOCATION_HISTORY")
    if not history_file or not pathlib.Path(history_file).is_file():
        raise ValueError(
            f"OSXPHOTOS_LOCATION_HISTORY not set or file does not exist: {history_file}"
        )

    delta = os.environ.get("OSXPHOTOS_LOCATION_DELTA", DEFAULT_TIME_DELTA)

    if LOCATION_HISTORY is None:
        verbose(f"Loading location history from {history_file}")
        LOCATION_HISTORY = LocationHistory(history_file)

    if photo.shared:
        # don't assume we were at location of shared photo
        return 0

    nearest_location, nearest_delta = LOCATION_HISTORY.nearest_location(photo.date)
    nearest_delta = int(nearest_delta)
    if nearest_delta >= delta:
        return 0

    verbose(
        f"Found location match for {photo.original_filename} taken on {photo.date} within {nearest_delta} seconds: {nearest_location['latitude']}, {nearest_location['longitude']}"
    )

    lat = nearest_location["latitude"]
    lon = nearest_location["longitude"]
    for result in results.exported:
        verbose(f"Adding location data to {result}")
        exiftool_add_location(result, photo, lat, lon)
    return 1


def exiftool_add_location(
    result: str, photo: PhotoInfo, lat: float, lon: float
) -> None:
    """Add location data to photo using exiftool

    Args:
        result: path to photo
        lat: latitude
        lon: longitude
    """
    exif = {}
    if photo.isphoto and not result.lower().endswith(".mov"):
        exif["EXIF:GPSLatitude"] = lat
        exif["EXIF:GPSLongitude"] = lon
        exif["EXIF:GPSLatitudeRef"] = "N" if lat >= 0 else "S"
        exif["EXIF:GPSLongitudeRef"] = "E" if lon >= 0 else "W"
    else:
        exif["Keys:GPSCoordinates"] = f"{lat} {lon}"
        exif["UserData:GPSCoordinates"] = f"{lat} {lon}"
    with ExifTool(result) as exiftool:
        for exiftag, val in exif.items():
            if type(val) == list:
                for v in val:
                    exiftool.setvalue(exiftag, v)
            else:
                exiftool.setvalue(exiftag, val)
        if exiftool.warning:
            click.echo(f"exiftool warning: {exiftool.warning}")
        if exiftool.error:
            click.echo(f"exiftool error: {exiftool.error}")


@click.command()
@click.argument("filename", type=click.Path(exists=True))
@click.option(
    "--delta",
    type=int,
    default=DEFAULT_TIME_DELTA,
    help=f"Time delta in seconds, default = {DEFAULT_TIME_DELTA}.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Dry run, do not actually update location info for photos.",
)
@click.option(
    "--add-to-album",
    metavar="ALBUM",
    help="Add updated photos to album named ALBUM, creating the album if necessary.",
)
def main(filename, delta, dry_run, add_to_album):
    click.echo(f"Version: {__version__}")
    click.echo(f"Loading history data from {filename}")
    location_history = LocationHistory(filename)
    click.echo(f"Loaded {len(location_history)} records")
    earliest = location_history.location_history[0]
    latest = location_history.location_history[-1]
    click.echo(
        f'Earliest: {earliest["datetime"]}, {earliest["latitude"]}, {earliest["longitude"]}'
    )
    click.echo(
        f'Latest: {latest["datetime"]}, {latest["latitude"]}, {latest["longitude"]}'
    )

    click.echo(f"Loading photo library")
    photosdb = PhotosDB()
    click.echo(f"Loaded {len(photosdb)} photos")

    photos = [
        photo
        for photo in photosdb.photos()
        if photo.location == (None, None) and not photo.shared
    ]
    album = PhotosAlbum(add_to_album, verbose=click.echo) if add_to_album else None
    click.echo(f"Checking {len(photos)} that lack location information")
    results = sum(
        add_location_to_photo(photo, location_history, delta, dry_run, album=album)
        for photo in photos
    )

    photo_str = "photo" if results == 1 else "photos"
    click.echo(f"Added location info to {results} {photo_str}")
    if add_to_album:
        click.echo(f"Photos added to album '{add_to_album}'")


if __name__ == "__main__":
    main()
