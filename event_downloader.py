import io
import os
import logging
import sys
import json
from datetime import datetime, timedelta
import filefunction as ff
from pathlib import Path
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Load local configuration without overriding Azure-provided environment variables.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

# Required runtime configuration.
API_KEY = os.environ["GOOGLE_DRIVE_API_KEY"]
FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
CURRENT_EVENTS_FILE = "events.json"


# Configure logging to output to stdout so Azure can capture
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("Lucky Liquor Event Processor")

# Build the Drive Service (Using developerKey for public access)
service = build("drive", "v3", developerKey=API_KEY)


def ListFilesInPublicFolder(folder_id):
    # Lists files in the target public folder on Google drive.
    files = []
    page_token = None

    # Query to find files where the specified folder is a parent
    query = f"'{folder_id}' in parents and trashed = false"
    #query = f"'{folder_id}'"

    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
            )
            .execute()
        )

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken", None)
        if not page_token:
            break

    return files


def DownloadFile(file_id, file_name):
    """Downloads a file by its ID."""
    logger.info(f"DownloadFile: Downloading {file_name}...")

    # Write the local file
    cwd = Path.cwd()
    to_save = cwd / "event_img" / file_name 
    temp_file = to_save.with_name(to_save.name + ".tmp")

    try:
        request = service.files().get_media(fileId=file_id)
        with io.FileIO(str(temp_file), "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f"Progress: {int(status.progress() * 100)}%")

        temp_file.replace(to_save)
    except Exception as e:
        logger.error(f"File download failed for {file_name} {e}")
        return None
    
    return file_name

def PurgeExpiredEvents(eventlist):
    # Removes events and their associated files that are older than today - 2 days
    # Returns a list of still current events
    current = []
    now = datetime.now()
    two_days_ago = now - timedelta(days=2)

    for event in eventlist:
        event_date = event["date"] + " 12:00:00"
        event_date_obj = datetime.strptime(event_date, "%m.%d.%y %H:%M:%S")
        if event_date_obj < two_days_ago:
            fname = event["filename"]
            logger.info(f"PurgeExpiredEvents removing {fname}")
            RemoveEventImage(fname)
        else:
            current.append(event)
    
    return current
        



def RemoveEventImage(imagename):
    cwd = Path.cwd()
    event_path = cwd / "event_img" / imagename
    event_path.unlink(missing_ok = True)


def BuildEventsFilePath():
    cwd = Path.cwd()
    new_path = cwd / "event_img"
    current_events = new_path / CURRENT_EVENTS_FILE
    return current_events


def WriteCurrentEvents(data):
    p = BuildEventsFilePath()
    filename = str(p)
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
        logger.info("WriteCurrentEvents wrote events.json")
    except Exception as e:
        logger.error(f"WriteCurrentEvents: Error writing file {e}")

def ReadCurrentEvents():
    p = BuildEventsFilePath()
    filename = str(p)
    data_list = []
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data_list = json.load(file)

    except Exception as e:
        logger.error(f"ReadCurrentEvents: Error reading current events file {e}")
        return None
    
    logger.info(f"ReadCurrentEvents found {len(data_list)} events.")
    return data_list

def MapAndCompareEvents(existing_events, new_events):
    old_map = {item["id"] : item for item in existing_events}
    new_map = {item["id"] : item for item in new_events}

    added = [item for item in new_events if item["id"] not in old_map]

    return added


def main():
    logger.info("Event Processor starting")
    
    items = []
    try:
        # Retrieve all items in the folder
        items = ListFilesInPublicFolder(FOLDER_ID)
        
    except Exception as e:
        logger.error(f"An error occurred retrieving files from Drive folder {FOLDER_ID}: {e}")
        return

    if not items:
        logger.info("Event Processor retrieved no files")
        new_events = []
    else:
        logger.info(f"Google drive lists {len(items)} items")
        new_events = ff.CreateFilesDictonary(items)

    existing_events = ReadCurrentEvents()
    if existing_events:
        current_events = PurgeExpiredEvents(existing_events)
    else:
        current_events = []

    # figure out which events we do not currrently have and download them
    events_to_add = MapAndCompareEvents(current_events, new_events)
    logger.info(f"Found {len(events_to_add)} new events to download")
    
    for e in events_to_add:
        fname = DownloadFile(e["id"], e["filename"])
        if fname:
            logger.info(f"DownloadFile: Successfully downloaded {fname}\n")
            current_events.append(e)
        else:
            logger.error(f"Error downloading {e['filename']}")

    sorted_events = sorted(current_events , key=lambda x: datetime.strptime(x["date"], "%m.%d.%y"))

    WriteCurrentEvents(sorted_events)

    logger.info("Events processor finished")

if __name__ == "__main__":
    main()
