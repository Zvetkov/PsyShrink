import os
import winreg
import logging

FALLBACK_WORKING_DIRECTORY = r"D:\GOG\Psychonauts"


def get_game_path(game_name, folder_name_check=None):
    steam_install_reg_path = r"SOFTWARE\WOW6432Node\Valve\Steam"
    hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
    try:
        # getting Steam installation folder from Reg
        steam_install_reg_value = winreg.OpenKey(hklm, steam_install_reg_path)
        steam_install_path = winreg.QueryValueEx(steam_install_reg_value, 'InstallPath')[0]

        # game can be installed in main Steam dir or in any of the libraries specified in config
        library_folders_config = os.path.join(steam_install_path, "SteamApps", "libraryfolders.vdf")
        library_folders = [steam_install_path]

        with open(library_folders_config, 'r') as f:
            supported_library_indexes = [f'"{i}"' for i in range(1, 11)]  # list of indexes in "0", "1" etc format
            lines = f.readlines()
            for line in lines:
                for index in supported_library_indexes:
                    # finding and cleaning any library folders found
                    if index in line:
                        directory = line.split('"		"')[1].strip().strip('"')
                        library_folders.append(directory)

        if not library_folders:
            logging.info("Library folders for Steam install not found, will try to use fallback working directory")
            return FALLBACK_WORKING_DIRECTORY

        for folder in library_folders:
            # checking that game install exist for this library and that data folder exists as well
            expected_game_path = os.path.join(folder, "SteamApps", "common", game_name)
            if folder_name_check is not None:
                if os.path.exists(expected_game_path):
                    if os.path.exists(os.path.join(expected_game_path, folder_name_check)):
                        # returining first dir found for the time being, TBD - let user choose from all found
                        return expected_game_path
    except FileNotFoundError:
        logging.info("Steam install not found, will try to use fallback working directory")

    return FALLBACK_WORKING_DIRECTORY


WORKING_DIRECTORY = get_game_path("Psychonauts", "WorkResource")
logging.info(f"'{WORKING_DIRECTORY}': choosen as game working directory")
