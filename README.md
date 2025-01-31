## LobbyLinks: Mapping the revolving door network

LobbyLinks is a python package that facilitates the extraction of valuable information from the DC lobbying network, including lobbyists' links to the 

There are two main data objects: the `LobbyData` object, which handles queries to the LDA database (https://lda.senate.gov/api/) and exports results to spreadsheets, and the `LobbyLinks` object, which packages a number of natural language processing routines used to extract links between lobbyists and congressional/Senate members.

The links to legislators depend on a database maintained by GovTrack, ProPublica, and a number of other organizations (https://github.com/unitedstates/congress-legislators). To update the legislators inventory, download the most recent versions of the following files from `congress-legislators` and insert them into the folder `lobbylinks/resources`:
* legislators-current.csv
* legislators-current.json
* legislators-historical.csv
* legislators-historical.json

### Installation
Run the following commands in sequence:
```
conda create --name lobbylinks python==3.7.9 -y && conda activate lobbylinks
bash installation.sh
```
The module has been tested in python version 3.7.99 and may not work in other settings.

To add GPU support for the NLP routines, change the versions of `tensorflow` and `spacy` to add relevant cuda versions.
