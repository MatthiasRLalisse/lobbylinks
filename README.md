## LobbyLinks: Mapping the revolving door network

LobbyLinks is a python package that facilitates the extraction of valuable information from the DC lobbying network, including lobbyists' links to the 

There are two main data structures: 
* The `LobbyData` object, which handles queries to the LDA database (https://lda.senate.gov/api/) and exports results to spreadsheets
* The `LobbyLinks` object, which packages a number of natural language processing routines used to extract links between lobbyists and congressional/Senate members. A `LobbyLinks` object also supports exporting visualizations of the lobby network in a `pyvis` format:

![exxon](https://github.com/user-attachments/assets/13d997a1-4c83-47e3-92b2-8119b6737ccf)

The links to legislators depend on a database maintained by GovTrack, ProPublica, and a number of other organizations (https://github.com/unitedstates/congress-legislators). To update the legislators inventory, download the most recent versions of the following files from `congress-legislators` and insert them into the folder `lobbylinks/resources`:

* `legislators-current.csv`
* `legislators-current.json`
* `legislators-historical.csv`
* `legislators-historical.json`

It is OK to overwrite these current contents of the `resources` folder. Note that `legislators-historical` is cumulative, but `legislators-current` is not.

### Installation
Run the following commands in sequence:
```
conda create --name lobbylinks python==3.7.9 -y && conda activate lobbylinks
bash installation.sh
```
The module has been tested in python version 3.7.9 and may not work in other settings.

To add GPU support for the NLP routines, change the versions of `tensorflow` and `spacy` to add relevant cuda versions.

### Using the package

See `lobby_query.py` for example usage. The parameter set used for API calls to the LDA database is the same as that documented at the LDA website (see `lobby_query_parameters_guide.pdf` for a list of fields which can be used to narrow a query). For a broad query for all filings for a given year, do the following:
```
from lobbylinks import LobbyData
q_auth = (my_api_username, my_api_key)

filing_year = [ 2024 ]
lobby_data = LobbyData(q_auth=q_auth, filing_year=filing_year) # scrape all filings for 2024. May take several hours.
groupby(['registrant_id' , 'filing_year', 'client', 'client_industry']).agg({'lobbyist_income': 'first', 'lobbyist_expenses': 'first', 'general_issue_code': set, 'general_issue': set})
lobby_data.merge_names() #optional: merges client names (e.g. EXXON MOBIL CORPORATE --> EXXON MOBIL)

lobby_data.summary.to_csv('lobby_filings_summary.csv') # export summary data for each filing
lobby_data.activity_summary.to_csv('lobby_filings_summary-by_activity.csv') # export summary data for each lobbying activity
```
`q_auth` can be set to `None` for small tasks (e.g. with narrow search terms for a single client), but you will need an API key if pulling all filings for a given year.

Income and expenditure for lobbying contracts is reported at the level of the filing (`lobby_data.summary`), while issues lobbied about and identities of involved lobbyists—including federal positions covered by the LDA , are reported at the level of the lobbying activity `lobby_data.activity_summary` Both levels may be of use depending on the analysis but money is not itemized at the level of the activity. Per-contract income is also reported in the `activity_summary` as the `lobbyist_income` and `lobbyist_expenses` columns, however since one report may encompass multiple activities, be sure not to double count. Issue codes within a contract/filing might be heterogeneous, but might be grouped together as:
```
# we get lobbying activity reports
activity = lobbying_data.activity_summary # pandas dataframe
# group activity reports by same filings, but aggregating the topics to a set
grouped_activity = activity.groupby(['registrant_id' ,
                                    'filing_year',
                                    'client',
                                    'client_industry']).agg({'lobbyist_income': 'first',
                                                             'lobbyist_expenses': 'first',
                                                             'general_issue_code': set,
                                                             'general_issue': set})
```
which exports the activity data to a new dataframe with a set of issue codes associated with each filing and its spending amount.

