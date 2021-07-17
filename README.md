# Add location to Apple Photos from Google Takeout Location History

Python script to add missing location data to photos in your Apple Photos library based on your [Google location history](https://takeout.google.com/settings/takeout/custom/location_history).  This script can be run stand-alone to add location data to the photos in your library or as a post-processing function for [osxphotos](https://github.com/RhetTbull/osxphotos) to add location data to photos upon export.

## Installation

Clone the repo:

- `git clone https://github.com/RhetTbull/add_photo_locations_from_google_history.git`
- `cd add_photo_locations_from_google_history`

I recommend you create and activate a python [virtual environment](https://docs.python.org/3/library/venv.html) before running pip:

- `python3 -m venv venv`
- `source venv/bin/activate`

Then install requirements:

- `python3 -m pip requirements.txt`

Requires python 3.7+

## Running

Download Google location history via [Google Takeout](https://takeout.google.com/settings/takeout/custom/location_history)

```
python3 add_photo_locations_from_google_history.py --help
Usage: add_photo_locations_from_google_history.py [OPTIONS] FILENAME

Options:
  --delta INTEGER       Time delta in seconds, default = 60.
  --dry-run             Dry run, do not actually update location info for
                        photos.
  --add-to-album ALBUM  Add updated photos to album named ALBUM, creating the
                        album if necessary.
  --help                Show this message and exit.
```

I strongly recommend you run with `--dry-run` first and manually check the locations for some of the photos.  I also recommend using the `--add-to-album` to add all updated photos to an album so you can check the results.  

`--delta` specifies how close in time (in seconds) the Google location history needs to be (in seconds) in order to match the location to the photo's timestamp.

## Running with osxphotos

To run with osxphotos to add missing location info in exported photos, use this as a parameter to `--post-function`.  You'll need to pass the path to your Google location history in the environment variable `OSXPHOTOS_LOCATION_HISTORY`:

`OSXPHOTOS_LOCATION_HISTORY="/path/to/Location History.json" osxphotos export /path/to/export -V --post-function add_photo_locations_from_google_history.py::add_location_to_photo_osxphotos`
