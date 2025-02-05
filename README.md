## LobbyLinks: Mapping the revolving door network

LobbyLinks is a python package that facilitates the extraction of valuable information from the DC lobbying network, including lobbyists' links to congressional offices.

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

See `lobby_query.py` for example usage. The parameter set used for API calls to the LDA database is the same as that documented at the LDA website (see `lobby_query_parameters_guide.pdf` for a list of fields which can be used to narrow a query). For a broad query of all filings for a given year, do the following:
```
from lobbylinks import LobbyData
q_auth = (my_api_username, my_api_key)

filing_year = [ 2024 ]
lobby_data = LobbyData(q_auth=q_auth, filing_year=filing_year) # scrape all filings for 2024. May take several hours.
lobby_data.merge_names() #optional: merges client names (e.g. EXXON MOBIL CORPORATE --> EXXON MOBIL)

lobby_data.summary.to_csv('lobby_filings_summary.csv') # export summary data for each filing
lobby_data.activity_summary.to_csv('lobby_filings_summary-by_activity.csv') # export summary data for each lobbying activity
```
`q_auth` can be set to `None` for small tasks (e.g. with narrow search terms for a single client), but you will need an API key if pulling all filings for a given year.

Income and expenditure for lobbying contracts is reported at the level of the filing (`lobby_data.summary`), while issues lobbied about and identities of involved lobbyists—including federal positions covered by the LDA , are reported at the level of the lobbying activity (`lobby_data.activity_summary`). Both levels may be of use depending on the analysis but money is not itemized at the level of the activity. Per-contract income is also reported in the `activity_summary` as the `lobbyist_income` and `lobbyist_expenses` columns, however since one report may encompass multiple activities, be sure not to double count. Issue codes within a contract/filing might be heterogeneous, so you can group them together as:
```
# we get lobbying activity reports
activity = lobbying_data.activity_summary # pandas dataframe
# group activity reports by same filings, but aggregating the topics to a set
grouped_activity = activity.groupby([
                                    'filing_id',
                                    'registrant_id' ,
                                    'filing_year',
                                    'filing_period',
                                    'client',
                                    'client_industry']).agg({'lobbyist_income': 'first',
                                                             'lobbyist_expenses': 'first',
                                                             'general_issue_code': set,
                                                             'general_issue': set})
```
which exports the activity data to a new dataframe with a set of issue codes associated with each filing and its spending amount.

### Matching legislators

The legislator-matching utility is provided by `lobbylinks.handlers.Legislators`. By default, all Senators and congressmembers since 1990 are loaded in, though for recent filing years it may be useful to constrain the list of legislators to a more recent year. We match to legislators using the `covered position` field of LDA disclosures, in which lobbyists must identify any position meeting the following criteria:
```
(4) COVERED LEGISLATIVE BRANCH OFFICIAL.-The term "covered legislative branch official" means-

(A) a Member of Congress;
(B) an elected officer of either House of Congress;
(C) any employee of, or any other individual functioning in the capacity of an employee of-
(i) a Member of Congress;
(ii) a committee of either House of Congress;
(iii) the leadership staff of the House of Representatives or the leadership staff of the Senate;
(iv) a joint committee of Congress; and
(v) a working group or caucus organized to provide legislative services or other assistance to Members of Congress; and
(D) any other legislative branch employee serving in a position described under section 109 (13) of the Ethics in Government Act of 1978 (5 U.S.C. App.).

Lobby Disclosure Act, PUBLIC LAW 104-65-DEC. 19,1995 109 STAT. 691
```
Since there is no temporal sunset clause on the position coverage, one will often find within LDA filings legislators whose term of service has long since passed. Our AI system for string-matching extracts links if a search term matches to *one and only one* legislator within the database, so a conservative strategy is to use the default of 1990, which may miss some links reported by younger lobbyists.

Internally, `Sen.` and `Rep.` prefixes occurring within a named entity parse are used to constrain the search to members of the respective chamber, and if multiple matches are found, no match is retrieved. For instance, there is only one, legislator with the name `Peters` in the Senate, while three House members share that name. If matching to the legislator database, a result is returned only if the chamber `branch='sen'` is specified:
```
legislators = lobbylinks.resources.handlers.Legislators(min_year=2022) # load in legislators from the 118th congress

legislators.best_match('Kelly', last_name=True) # multiple matches, returns None

legislators.best_match('Kelly', last_name=True, branch='sen')
>>> {'id': {'bioguide': 'P000595', 'thomas': '01929', 'govtrack': 412305, 'opensecrets': 'N00029277', 'votesmart': 8749, 'fec': ['H8MI09068', 'S4MI00355'], 'cspan': 50199, 'wikipedia': 'Gary Peters', 'house_history': 20028, 'ballotpedia': 'Gary Peters', 'maplight': 787, 'icpsr': 20923, 'lis': 'S380', 'wikidata': 'Q1494930', 'google_entity_id': 'kg:/m/02x0lnt', '__dict__': {...}, 'CAND_ID': ['CAND001599']}, 'name': {'first': 'Gary', 'middle': 'C.', 'last': 'Peters', 'official_full': 'Gary C. Peters', '__dict__': {...}}, 'bio': {'gender': 'M', 'birthday': '1958-12-01', '__dict__': {...}}, 'terms': [{'type': 'rep', 'start': '2009-01-06', 'end': '2011-01-03', 'state': 'MI', 'district': 9, 'party': 'Democrat', 'url': 'http://peters.house.gov', '__dict__': {...}}, {'type': 'rep', 'start': '2011-01-05', 'end': '2013-01-03', 'state': 'MI', 'district': 9, 'party': 'Democrat', 'url': 'http://peters.house.gov', 'address': '1609 Longworth HOB; Washington DC 20515-2209', 'phone': '202-225-5802', 'fax': '202-226-2356', 'contact_form': 'https://forms.house.gov/peters/contact-form.shtml', 'office': '1609 Longworth House Office Building', '__dict__': {...}}, {'type': 'rep', 'start': '2013-01-03', 'end': '2015-01-03', 'state': 'MI', 'party': 'Democrat', 'district': 14, 'url': 'http://peters.house.gov', 'address': '1609 Longworth HOB; Washington DC 20515-2214', 'phone': '202-225-5802', 'fax': '202-226-2356', 'contact_form': 'https://petersforms.house.gov/contact-us-form', 'office': '1609 Longworth House Office Building', 'rss_url': 'http://peters.house.gov/common/rss/?rss=22', '__dict__': {...}}, {'type': 'sen', 'start': '2015-01-06', 'end': '2021-01-03', 'state': 'MI', 'class': 2, 'state_rank': 'junior', 'party': 'Democrat', 'url': 'https://www.peters.senate.gov', 'address': '724 Hart Senate Office Building Washington DC 20510', 'office': '724 Hart Senate Office Building', 'phone': '202-224-6221', 'contact_form': 'https://www.peters.senate.gov/contact/email-gary', 'fax': '202-226-2356', '__dict__': {...}}, {'type': 'sen', 'start': '2021-01-03', 'end': '2027-01-03', 'state': 'MI', 'class': 2, 'state_rank': 'junior', 'party': 'Democrat', 'url': 'https://www.peters.senate.gov', 'contact_form': 'https://www.peters.senate.gov/contact/email-gary', 'address': '724 Hart Senate Office Building Washington DC 20510', 'office': '724 Hart Senate Office Building', 'phone': '202-224-6221', '__dict__': {...}}], 'currently_in_office': 'True', '__dict__': {...}, 'index': 222, 'full_name': 'Gary C. Peters', 'was_house': True, 'was_senate': True, 'was_exec': False, 'first_house_term_start': '2009-01-06', 'first_sen_term_start': '2015-01-06', 'first_term_start': '2009-01-06'}

legislators.best_match('Kelly', last_name=True, branch='rep') # 3 matching House members, returns None
```
When calling `Legislators` within a `LobbyLinks` graph build, potential legislators are identified using a stringent unique-match criterion, but a good workflow to catch rare errors is to to auto-build the `LobbyLinks` object from a filings dataset, export the graph to csv, make any manual adjustments to the matches, and then load in the pre-built graph to a new `LobbyLinks` object:
```
lobby_links = LobbyLinks(lobby_filing_data) # filing data should be a `LobbyData` object
# the graph will be built via name-matching to the legislators

# export the graph to csv
lobby_links.graph.to_csv('lobby_graph.csv')

# import the graph after annotation tasks
lobby_links = LobbyLinks(graph=pd.read_csv('lobby_graph+annotations.csv'))
lobby_links.visualize().show('lobby_graph_viz.html')
```



