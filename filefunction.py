

import logging
import sys
import re
from pathlib import Path


logging.basicConfig(
level=logging.INFO,
format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
handlers=[
    logging.StreamHandler(sys.stdout)
]
)

logger = logging.getLogger("Lucky Liquor Event Processor")

def CreateFilesDictonary(file_items):
    # Takes a list of strings containing a date and a filename and turns them into a list of dictionary objects
    # Only processes .jpg files. Other types skipped
    logger.info(f"CreateFilesDictonary: processing {len(file_items)} items.")
    file_list = []
    for f in file_items:

        name = f.get("name")
        id = f.get("id")
        if not name or not id:
            logger.info("CreateFilesDictionary: invalid entry received.")
            continue

        if Path(name).suffix != ".jpg":
            logger.info(f"CreateFilesDictionary: skipping {name}")
            continue
        
        event_info = SplitFilename(name, id)
        if event_info is None:
            continue

        file_list.append(event_info)

    logger.info(f"CreateFilesDictonary: processed {len(file_list)} items.")
    return file_list





def SplitFilename( name, id):
    # Takes a filename retrived from the server and splits it into date, bandnames, and filename extension.
    # Returns a dictonary item
    entry = {}
    match = re.fullmatch(r"(\d{2}\.\d{2}\.\d{2})\s+(.+)\.([^.]+)", name)
    if match:
        date, bands, extension = match.groups()
        entry["filename"] = name
        entry["date"] = date
        entry["bandnames"] = bands
        entry["id"] = id
        entry["extension"] = extension      
    else:
        logger.info(f"SplitFilename: could not process {name}.")
        entry = None
    
    return entry
    
        



def main():

    dummy_file_list = [
        { "name" : "11.12.26 Public Witness, Walter Moses Band, Neon Stills, Nothing Less Than Angels.jpg", "id": "(1Z6ywnrQYFyh1cnVRyIsPik0ZFYrS20qI)"},
        { "name" : "11.27.26 Das Vulture (The Fall cover set), Area 51 (Dead Moon cover set), The Fairweather Friends (Wipers cover set).jpg","id": "(11dbSxLeTDUIbywXwXtv-RcwgSDbN-N9v)"},
        { "name" : "12.12.26 F.O.T.Fest.jpg", "id": "(11dbSxLeTDUIbywXwXtv-RcwgSDbN-N9v)"},
        { "name" : "12.11.26 F.O.T.Fest.jpg", "id": "(11dbSxLeTDUIbywXwXtv-RcwgSDbN-N9v)"},
        { "name" : "11.07.26 Bottom Blade, Festering Estate, Cujo, Sneer.jpg", "id": "(11dbSxLeTDUIbywXwXtv-RcwgSDbN-N9v)"},
        { "name" : "11.20.26 Brain Cell Genocide, Electric Head, Culmination, Swamp Ass.jpg", "id": "(11dbSxLeTDUIbywXwXtv-RcwgSDbN-N9v)"},
    ]

    logger.info("Event Processor starting")
    count = len(dummy_file_list)
    try:
        # Retrieve all items in the folder
        # items = list_files_in_public_folder(FOLDER_ID)
        events = CreateFilesDictonary(dummy_file_list)

        for e in events:
           print(e)

        

    except Exception as e:
        print(f"An error occurred: {e}")

    print(f"Processed {count} events") 

if __name__ == "__main__":
    main()
