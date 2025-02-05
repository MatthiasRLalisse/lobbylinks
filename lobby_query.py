###LDA database query from API and build LobbyLinks graph
from lobbylinks.resources.handlers import IssueCodes, Legislators 	#utilities for handling resources
from lobbylinks import LobbyData, LobbyLinks	#core utilities

q_auth = None #swap in credentials for LDA API (needed for large queries)
# q_auth = (my_api_username, my_api_passkey)
# register for an API key here: https://lda.senate.gov/api/register/

filing_year = [2022, 2024]
client_name = 'exxon'

#query the LDA API for lobby report filings matching search criteria
lobby_data = LobbyData(q_auth=q_auth, filing_year=filing_year, client_name=client_name, client_country='US') 
# export filings to csv
lobby_data.merge_names() #optional: merges client names (e.g. EXXON MOBIL CORPORATE --> EXXON MOBIL)
lobby_data.summary.to_csv('lobby_filings_summary.csv')
lobby_data.activity_summary.to_csv('lobby_filings_summary-by_activity.csv')


#extract links & create the graph in pandas table format (csv-convertible)
lobby_links = LobbyLinks(lobby_data, verbose_build=False)
		#if verbose_build, print incremental results
		#good for spot-checking legislator extraction

# export the graph as a CSV
lobby_links.graph.to_csv('lobby_graph.csv')

graph_viz = lobby_links.visualize('lobby_graph.html')

