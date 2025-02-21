#LDA database utils

from .resources.handlers import AttrDict, Legislators, \
                                IssueCodes, lobby_namesort, \
                                LegislatorExtractor, CompanyMatcher

#basic imports
import re, os, json
from collections import defaultdict
import requests #for calls to API
import pickle #for saving LobbyData objects
from tqdm import tqdm
from copy import deepcopy
from functools import cmp_to_key
import time

#custom utilities
from .utils import TimeOutHandler, DummyTimeout, build_queries, \
                   exact_search_filter, _is_initials, \
                   _has_numerical_suffix, proc_name, \
                   get_filing_summary, get_activity_summary, \
                   get_feca_filing_summary, get_contribution_summary

#minimize tensorflow printouts
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

#data processing inputs
import numpy as np
import pandas as pd
import networkx as nx
from pyvis.network import Network

try: import wordninja
except ModuleNotFoundError: print('do \'pip install wordninja\' for extra postprocessing or set ninja_postproc=False')

def get_results(r_data, filt):
  try:
    new_results = [ AttrDict(filing) for filing in 
                        r_data['results'] if filt(filing) ]
  except KeyError: 
    new_results = []
  return new_results

def load(fname):
  with open(fname, 'rb') as f:
    return pickle.load(f)


class LobbyData(object):
  """wrapper for queries to the LDA REST database API\n"""\
  """Performs query upon initialization. All keywords are passed to the API call.\n"""\
  """See lobby_query_parameters.odt or LDA API documentation for guide to valid kwargs."""
  """Supports slicing, addition (filing concatenation), and inplace addition."""
  def __init__(self, save_file=None, query_auth=None, \
                     load_from_save=False, _filings=None, 
                     paginate_wait=3, **kwargs):
    self.save_file = save_file
    assert paginate_wait is None or isinstance(paginate_wait, (int,float))
    self.paginate_wait = paginate_wait
    if save_file is not None and load_from_save:
      try:
        with open(save_file, 'rb') as pkl_file:
          self = pickle.load(pkl_file)
        print('loaded LobbyData from %s' % save_file)
        loaded = True
      except FileNotFoundError:
        print('could not find save file. building data from query')
        loaded = False
    else: loaded = False
    if not loaded:
      self.issue_codes = IssueCodes()
      if _filings is None:
        print('querying LDA database with query params')
        self.filings = self.query_LDAdb(query_auth, **kwargs)
        print('found %i results for this query' % len(self.filings))
      else:
        self.filings = _filings
      #print('filings', self.filings)
      #self.summary = self.compile_summary()
      self._strip_duplicates()
    self.companyMatcher = CompanyMatcher()
    
  def query_LDAdb(self, query_auth=None, **kwargs):
    #self.save_file = None
    #query_auth is a tuple (username, password) for registered LDA API users
    print('querying https://lda.senate.gov API')
    kwargs['page_size'] = 25
    try:
      year_range = kwargs['filing_year']
      if type(year_range) in [list, tuple]:
        year_range = range(int(min(year_range)), 
                           int(max(year_range)+1))
      elif type(year_range) in [int, str]:
        year_range = [year_range]
    except KeyError: year_range = ['']
    filings_server = 'https://lda.senate.gov/api/v1/filings/' #main dir for filings
    query = lambda q_parameters: requests.get(filings_server, \
                   auth=query_auth, params=q_parameters)
    #print('query parameters', kwargs)
    all_results = []
    #for filing_year in year_range:
    for kwargs_ in build_queries(kwargs):
      #kwargs_ = kwargs.copy()
      #kwargs_['filing_year'] = filing_year
      print('\ncurrent query', kwargs_, '\n')
      r = query(kwargs_) #initial query
      r_data = r.json()
      filt = exact_search_filter(kwargs_)
     
      new_results = get_results(r_data, filt)
      #try:
      #  new_results = [ AttrDict(filing) for filing in 
      #                      r_data['results'] if filt(filing) ]
      #except KeyError: 
      #  new_results = []
      
      #iterate on 'next' to get all results matching the query
      while len(new_results) > 0:
        all_results += new_results
        print('%i results received\r' % len(all_results), end='')
        if self.paginate_wait is not None:
            time.sleep(self.paginate_wait)
        
        new_results = get_results(r_data, filt)
        try:
          if r_data['next'] is None:
            break
        except KeyError:
          break
        r_ = requests.get(r_data['next'], auth=query_auth)
        try:
          r_data = r_.json()
        except: # json.decoder.JSONDecodeError:
          #print(r_data)
          #break
          #raise json.decoder.JSONDecodeError
          pass
        #new_results = [ AttrDict(filing) for filing 
        #                    in r_data['results'] if filt(filing) ]
      #filter for any exact string searches
    return all_results
  
  def update(self, **kwargs):
      print('current filings', len(self.filings))
      new_filings = self.query_LDAdb(**kwargs)
      print('found %i results for this query' % len(new_filings))
      self.filings += new_filings
      print('updated filings', len(self.filings))
      #self.summary = self.compile_summary()
      if self.save_file is not None:
        self.save()
  
  def merge_names(self, companyMatcher=CompanyMatcher(), inplace=True):
    #merges company names using companyMatcher object, using the
    #	heuristics in resources.match_heuristics by default
    #take the shortest name in the list of reduced names that actually occurred in the dataset
    #merged_filings = []
    merges = {}; merge_count = 0
    for filing in tqdm(self.filings):
      #new_filing = filing.copy()
      client_name = filing.client.name
      filing.client.name__merged_from_ = client_name
      
      try: #if client_name in merges:
          merged_name = merges[client_name]
      except KeyError:
          merged_name = companyMatcher.reduce(client_name)
          merges[client_name] = merged_name
      if client_name != merged_name: #merge_count += 1
        filing.client.name = merged_name
        merges[client_name] = merged_name
    self.merges = merges
    n_pre_merge = len(set([ filing.client.name__merged_from_ \
                                                for filing in self.filings ]))
    n_post_merge = len(set([ filing.client.name for filing in self.filings ]))
    print('merged %i clients to %i clients' % (n_pre_merge, n_post_merge))
      #merged_filings.append(AttrDict(new_filing))
    #if inplace:
    #  self.filings = merged_filings
    #else:
    #  return merged_filings
  
  def reset_names(self):
    for filing in self.filings:
      current_name = filing.client.name
      try:
        filing.client.name = filing.client.name__merged_from_
        del filing.client.name__merged_from_
      except AttributeError: pass
  
  def _strip_duplicates(self):
    #remove duplicate entries in-place
    criteria2idx = defaultdict(list)
    criteria = ('filing_uuid', 'url', 'filing_document_url')
    for i, filing in enumerate(self):
      criteria2idx[ tuple( filing[crit] for crit in criteria) ].append(i)
    
    self.filings = [ self[dupl[-1]] for dupl in criteria2idx.values() ]
    
  def __len__(self):
    return len(self.filings)
  
  def __getitem__(self, i):
    return self.filings[i]
  
  def concat(self, lobby_data):
    assert type(lobby_data) == LobbyData
    self.filings += lobby_data.filings
  
  @property
  def clients(self):
    #returns the set of all clients found in the dataset
    return set([ filing.client.name for filing in self ])
  
  def apply_filter(self, boolean_function, inplace=False):
    #filter out all filings (in-place) such that
    #	boolean_function(filings) != True
    new_filings = []
    for filing in self:
      if boolean_function(filing):
        new_filings.append(filing)
    if inplace:
      self.filings = new_filings
    else: 
      return type(self)(_filings = new_filings)
  
  @property
  def summary(self):
    #compute summary dataframe per-filing
    summary_data = defaultdict(list)
    for N, filing in enumerate(self):
      for key, val in get_filing_summary(filing).items():
        summary_data[key].append(val)
      
      summary_data['filing_index'].append(N)
      #add an entry for income (lobby firm) + expenses (in-house)
      #income = float(filing.income) if filing.income is not None else 0
      #expenses = float(filing.expenses if filing.expenses is not None else 0
      #summary_data['total_spend'].append(income+expenses)
    ###add functionality to summarize each lobbying activity, with topics etc?
    return pd.DataFrame(summary_data)
  
  @property
  def activity_summary(self):
    #compute summary dataframe per-lobby activity (intra-filing)
    summary_data = defaultdict(list)
    for N, filing in enumerate(self):
      if hasattr(filing, 'lobbying_activities'):
        filing_summary = get_filing_summary(filing)
        activities = filing.lobbying_activities
        #add an entry for income (lobby firm) + expenses (in-house)
        for entry in activities:
          activity_summary = get_activity_summary(entry)
          for key, val in filing_summary.items():
            summary_data[key].append(val)
          for key, val in activity_summary.items():
            summary_data[key].append(val)
          summary_data['filing_index'].append(N)
    return pd.DataFrame(summary_data)
  
  def _filing_priority(self, filing1, filing2):
    #defines priority for filings; amendments > original 
    #filings and then ranked according to posting date
    #used downstream in self.merge_amended()
    if filing2.filing_type_display.endswith('Amendment') \
               and filing1.filing_type_display.endswith('Report'):
       return True
    elif filing1.dt_posted <= filing2.dt_posted:
       return True
    else:
       return False
  
  @property
  def _criteria2idx(self):
    criteria2idx = defaultdict(list)
    for i, filing in enumerate(self):
      criteria2idx[filing.registrant.name, \
                   filing.filing_year, \
                   filing.filing_period, \
                   filing.client.name, \
                   #tuple(filing.affiliated_organizations)
                   ].append((filing.filing_type, i))
    return criteria2idx
  
  def merge_amended(self, inplace=True):
    #aggregate merge criteria: registrant, filing_year, filing_period
    
    criteria2idx = self._criteria2idx
    #take the last-posted amended version of each filing that is
    #	identical according to the criteria in criteria2idx
    #	with self._filing_priority as mapping function for sorted
    key = cmp_to_key(self._filing_priority)
    if inplace:
      self.filings = [ sorted([ self[idx] for type_, idx in filing_idx_ ], \
                       key=key)[-1] for filing_idx_ in criteria2idx.values() ]
    else: 
      _filings = [ sorted([ self[idx] for type_, idx in filing_idx_ ], \
                   key=key)[-1] for filing_idx_ in criteria2idx.values() ]
      return type(self)(_filings=_filings)
  
  def __getstate__(self):
    return vars(self)
  
  def __setstate__(self, state):
    vars(self).update(state)
  
  def __iadd__(self, b):
    assert isinstance(b, LobbyData)
    #out_self = copy.deepcopy(self)
    #out_self._tweets += b._tweets
    self.filings += b.filings
    self._strip_duplicates()
    return self
  
  def __add__(self, b):
    assert isinstance(b, LobbyData)
    _cat_filings = self.filings + b.filings
    return LobbyData(_filings=_cat_filings)
  
  def save(self, save_file=None):
    assert save_file is not None or self.save_file is not None
    save_file = self.save_file if save_file is None else save_file
    with open(save_file, 'wb') as out_file:
      pickle.dump(self, out_file, pickle.HIGHEST_PROTOCOL) 


class ContributionsData(LobbyData):
  """wrapper for queries to the LDA FECA contributions database"""
  """Performs query upon initialization. All keywords are passed to the API call.\n"""\
  """See lobby_query_parameters.odt or LDA API documentation for guide to valid kwargs."""
  """Supports slicing, addition (filing concatenation), and inplace addition."""
  def __init__(self, save_file=None, query_auth=None, \
                     load_from_save=False, _filings=None, **kwargs):
    super(ContributionsData, self).__init__(save_file=save_file, query_auth=query_auth, 
                                            load_from_save=load_from_save, 
                                            _filings=_filings,
                                            **kwargs)
  def query_LDAdb(self, query_auth=None, **kwargs):
    #self.save_file = None
    #query_auth is a tuple (username, password) for registered LDA API users
    print('querying https://lda.senate.gov FECA Contributions API')
    kwargs['page_size'] = 25 # max
    try:
      year_range = kwargs['filing_year']
      if type(year_range) in [list, tuple]:
        year_range = range(int(min(year_range)), 
                           int(max(year_range)+1))
      elif type(year_range) in [int, str]:
        year_range = [year_range]
    except KeyError: year_range = ['']
    filings_server = 'https://lda.senate.gov/api/v1/contributions/' #main dir for filings
    query = lambda q_parameters: requests.get(filings_server, \
                   auth=query_auth, params=q_parameters)
    all_results = []
    #for filing_year in year_range:
    for kwargs_ in build_queries(kwargs):
      #kwargs_ = kwargs.copy()
      #kwargs_['filing_year'] = filing_year
      print('\ncurrent query', kwargs_, '\n')
      r = query(kwargs_) #initial query
      r_data = r.json()
      filt = exact_search_filter(kwargs_)
      
      new_results = get_results(r_data, filt)
      #iterate on 'next' to get all results matching the query
      while len(new_results) > 0:
        all_results += new_results
        print('%i results received\r' % len(all_results), end='')
        if self.paginate_wait is not None:
            time.sleep(self.paginate_wait)
        
        new_results = get_results(r_data, filt)
        try:
          if r_data['next'] is None:
            break
        except KeyError:
          break
        r_ = requests.get(r_data['next'], auth=query_auth)
        r_data = r_.json()
        #new_results = [ AttrDict(filing) for filing 
        #                    in r_data['results'] if filt(filing) ]
      #filter for any exact string searches
    return all_results
  
  def merge_names(self, companyMatcher=CompanyMatcher(), inplace=True):
    #merges company names using companyMatcher object, using the
    #	heuristics in resources.match_heuristics by default
    #take the shortest name in the list of reduced names that actually occurred in the dataset
    #merged_filings = []
    merges = {};
    contributor_merges = {}
    all_contributors = set()
    for filing in self.filings:
      #new_filing = filing.copy()
      registrant_name = filing.registrant.name
      filing.registrant.name__merged_from_ = registrant_name
      merged_name = companyMatcher.reduce(registrant_name)
      if registrant_name != merged_name: #merge_count += 1
        filing.registrant.name = merged_name
        merges[registrant_name] = merged_name
      for contribution in filing.contribution_items:
        contributor = contribution.contributor_name
        all_contributors.add(contributor)
        contribution.contributor_name__merged_from_ = contributor
        merged_name = companyMatcher.reduce(contributor)
        if contributor != merged_name:
          contribution.contributor_name = merged_name
          contributor_merges[contributor] = merged_name
    self.merges = merges
    self.contributor_merges = contributor_merges
    n_pre_merge = len(set([ filing.registrant.name__merged_from_ \
                                                for filing in self.filings ]))
    n_post_merge = len(set([ filing.registrant.name for filing in self.filings ]))
    print('merged %i registrants to %i registrants' % (n_pre_merge, n_post_merge))
    print('merged %i contributors to %i contributors' % \
                     (len(all_contributors), len(all_contributors) \
                                                 - len(contributor_merges)))
  
  def reset_names(self):
    for filing in self.filings:
      current_name = filing.registrant.name
      try:
        filing.client.name = filing.registrant.name__merged_from_
        del filing.registrant.name__merged_from_
      except AttributeError: pass
  
  def concat(self, lobby_data):
    assert type(lobby_data) == ContributionsData
    self.filings += lobby_data.filings
  
  @property
  def registrants(self):
    #returns the set of all clients found in the dataset
    return set([ filing.registrant.name for filing in self ])
  
  @property
  def summary(self):
    #compute summary dataframe per-filing
    summary_data = defaultdict(list)
    for filing in self:
      for key, val in get_feca_filing_summary(filing).items():
        summary_data[key].append(val)
    return pd.DataFrame(summary_data)
  
  @property
  def contributions_summary(self):
    #compute summary dataframe per-lobby activity (intra-filing)
    summary_data = defaultdict(list)
    for filing in self:
      if hasattr(filing, 'contribution_items'):
        filing_summary = get_feca_filing_summary(filing)
        contributions = filing.contribution_items
        for entry in contributions:
          contribution_summary = get_contribution_summary(entry)
          for key, val in filing_summary.items():
            summary_data[key].append(val)
          for key, val in contribution_summary.items():
            summary_data[key].append(val)
    return pd.DataFrame(summary_data)
  
  @property
  def _criteria2idx(self):
    criteria2idx = defaultdict(list)
    for i, filing in enumerate(self):
      criteria2idx[filing.registrant.name, \
                   filing.filing_year, \
                   filing.filing_period, \
                   filing.filer_type, \
                   tuple(filing.pacs), \
                   (filing.lobbyist.id if filing.lobbyist \
                                       is not None else None), \
                   ].append((filing.filing_type, i))
    return criteria2idx
  
  def __iadd__(self, b):
    assert isinstance(b, ContributionsData)
    #out_self = copy.deepcopy(self)
    #out_self._tweets += b._tweets
    self.filings += b.filings
    self._strip_duplicates()
    return self
  
  def __add__(self, b):
    assert isinstance(b, ContributionsData)
    _cat_filings = self.filings + b.filings
    return ContributionsData(_filings=_cat_filings)

othtitles_ = [ 'Chairman', 'Chair', 'Chrmn', 'Chr', 'Chairwoman', 'Chrwm', 'Chrwmn' ]

class LobbyLinks(object):
  """main object for building client-congress links\n"""
  """arg:\n"""
  """\tdata - a LobbyData object\n"""
  """kwargs:\n"""
  """\tlegislators_handler - handlers.Legislators object, which can be passed """
  """if you would like a different min_year than 1990 (default) with e.g. """
  """LobbyLinks(legislators_handler=Legislators(min_year=2008)). Retrieves"""
  """legislators from min_year up to the present.\n"""
  """\tverbose_build - Boolean, False by default. Prints name extraction and"""
  """matching results. Good for spot-checking extraction outputs."""
  def __init__(self, data=None, save_file=None, legislators_handler=None, 
                           issue_codes=None, verbose_build=False, 
                           merge_names=True, spacy_model='en_core_web_trf', 
                           companyMatcher=CompanyMatcher, ninja_postproc=True, 
                           graph=None):
    assert isinstance(data, LobbyData) or data == None, "input must be a LobbyData object"
    if data is None:
        assert graph is not None, "either input a LobbyData object or the pre-built graph as a pandas dataframe (kwarg `graph`)"
    self.save_file = save_file
    self.ninja = ninja_postproc
    if issue_codes is not None:
      #can filter "lobbying_activities" for just those with
      #filing.general_issue_code matching a list of issue codes
      if isinstance(issue_codes, str):
        issue_codes = [ issue_codes ]
    self.incl_codes = issue_codes
    
    #self.timeout = DummyTimeout()
    self.timeout = TimeOutHandler(timeout=5) #sets 5-second timeout for name-matching step
    
    if legislators_handler is None: 
      #default settings: only legislators who were in office in 1990
      #can pass a different object, e.g. Legislators(min_year=2008)
      legislators_handler = Legislators() #handler for legislators
    self.filing_data = data
    #if merge_names:
    #  self.filing_data.merge_names(companyMatcher=companyMatcher)
    self.issue_codes = IssueCodes()
    #self.name_extractor = NEExtractor()
    self.legislator_extractor = LegislatorExtractor(spacy_model=spacy_model)
    self.legislators = legislators_handler
    if graph is None:
      self.graph = self.make_graph(verbose_build=verbose_build)
    else: self.graph = graph
  
  def make_graph(self, verbose_build=False):
    graph_data = defaultdict(list)
    graph_fields = [ 'client_name', 'legislator', 'edge_type', 'title', 'party', \
                     'confidence', 'client_industry', 'contract_value', \
                     'issue_name', 'issue_description', 'issue_code', 'lobbyist_id', \
                     'lobbyist_name', 'currently_in_office', 'link_source_text', 
                     'legislator_icpsr', 'legislator_govtrack', 'legislator_bioguide', 
                     'legislator_thomas', 'filing_year', 'client_name_unmerged_',
                     'income_per_lobbyist', 'registrant_id', ]
                     #later runs eval(name) on each varname
    
    print('building lobby network')
    # speed things up by tracking already identified text
    text2legislator_idx = {}
    covered_position2names = {}
    
    for N, filing in enumerate(tqdm(self.filing_data.filings)):
      client_name = filing.client.name
      
      #lobbyist_id = filing.registrant.id
      client_industry = str(filing.client.general_description)
      contract_value = (float(filing.income) if filing.income is not None else 0)
      activities = filing.lobbying_activities
      filing_year = filing.filing_year
      registrant_id = filing.registrant.id
      if hasattr(filing.client, 'name__merged_from_'):
          client_name_unmerged_ = filing.client.name__merged_from_
      else:
          client_name_unmerged_ = filing.client.name
      for activity in activities:
        issue_description = activity.description
        issue_code = activity.general_issue_code
        issue_name = self.issue_codes[issue_code]
        lobbyists = activity.lobbyists
        lobbyist_ids_ = set([ l.lobbyist.id for l in lobbyists ])
        if self.incl_codes is None or issue_code in self.incl_codes:
          for lobbyist in lobbyists:
            lobbyist_id = lobbyist.lobbyist.id
            lobbyist_name = ' '.join([ lobbyist.lobbyist[k] for k in \
                                lobby_namesort(lobbyist.lobbyist) if \
                                lobbyist.lobbyist[k] is not None ])
            covered_position = lobbyist.covered_position
            link_source_text = covered_position
            income_per_lobbyist = contract_value/len(lobbyist_ids_)
            if covered_position is not None:
              try:
                  linked_names = covered_position2names[covered_position]
              except KeyError:
                  linked_names = self.legislator_extractor.extract(covered_position)
                  covered_position2names[covered_position] = linked_names
              for name, (branch, length) in linked_names.items():
                if verbose_build:
                  print('scoring %s %s' % (branch, name))
                _proc_name = lambda: proc_name(name, length)
                #	wraps name processing to enable timeout
                processed_name = self.timeout.wrap(_proc_name)
                print(name, branch, length, processed_name)
                #	fixes some common errors with NER output
                if processed_name is not None:
                  name, length = processed_name
                  try:
                    # try to retrieve match output if it already exists
                    #leg_id, score_ = text2legislator_idx[(name, branch, length)]
                    match_output = text2legislator_idx[(name, branch, length)]
                    if match_output is not None:
                      leg_id, score_ = match_output
                      match_output = (self.legislators[leg_id], score_)
                    
                    #match_output = text2legislator_idx[(name, branch length)]
                  except KeyError:
                    #try to find a match among legislators, else pass
                    last_name = True if length < 2 else False
                    match_fn = lambda: self.legislators.best_match(name, \
                                            last_name=last_name, \
                                            branch=branch, return_score=True, \
                                            filing_year=filing_year, \
                                            verbose=verbose_build)
                    match_output = self.timeout.wrap(match_fn)
                    
                    for oth in othtitles_:
                      if match_output is None or match_output[0] is None:
                        name_ = re.sub(r'^'+oth, '', name, flags=re.IGNORECASE)
                        if name_ != name:
                          match_output = self.timeout.wrap(match_fn)
                    
                    # if no results are returned, try a wordninja string split
                    if self.ninja and (match_output is None or match_output[0] is None):
                      ninja_name = ' '.join(wordninja.split(name))
                      ninja_names_ = self.legislator_extractor.extract(ninja_name)
                      #print('ninja', ninja_name, ninja_names_)
                      for name, (_, length) in ninja_names_.items():
                        #try to find a match among legislators, else pass
                        last_name = True if length < 2 else False
                        match_fn = lambda: self.legislators.best_match(name, \
                                                last_name=last_name, \
                                                branch=branch, return_score=True, \
                                                filing_year=filing_year, \
                                                verbose=verbose_build)
                        match_output = self.timeout.wrap(match_fn)
                        if match_output is not None and match_output[0] is not None:
                          if verbose_build > 1:
                            print(f'\tninja matched \"{name}\" substring')
                          break
                    
                    if match_output is not None:
                      match, score = match_output
                      if match is not None:
                        text2legislator_idx[(name, branch, length)] = (match.index, score)
                      else:
                        text2legislator_idx[(name, branch, length)] = None
                    else:
                      text2legislator_idx[(name, branch, length)] = None # store no match
                  
                  if match_output is not None:
                    match, score = match_output
                    #print(match)
                    #
                    if match is not None:
                      title = 'Sen. ' if match.was_senate else \
                             ('Rep. ' if match.was_house else '') 
                                          #title of highest office
                      legislator = title + match.full_name
                      confidence = score
                      currently_in_office = float(eval(match.currently_in_office))
                      legislator_icpsr = match.id.icpsr if hasattr( \
                                         match.id, 'icpsr') else None
                      legislator_govtrack = match.id.govtrack if hasattr( \
                                            match.id, 'govtrack') else None
                      legislator_bioguide = match.id.bioguide if hasattr( \
                                            match.id, 'bioguide') else None
                      legislator_thomas = match.id.thomas if hasattr( \
                                          match.id, 'thomas') else None
                      
                      edge_type = 'ClientOfLobbyistLinkedTo' #edge from client of 
                                                             #lobbyist to lobbyist's links 
                                                             #via covered_positions
                      party = match.terms[-1].party #political party in most recent term
                      #add an entry to the graph_data dict
                      if verbose_build:
                        print('matched', match.full_name)
                      for field in graph_fields:
                        graph_data[field].append(eval(field)) #append the extracted values
                      graph_data['filing_index'].append(N)
                  else:
                    if verbose_build: print('no match 1')
                else:
                  if verbose_build: print('timed out 2')
                if verbose_build > 1: print('source text:', covered_position)
    GraphData = pd.DataFrame(graph_data)
    return GraphData
  
  def save(self, save_file=None):
    assert save_file is not None or self.save_file is not None
    save_file = self.save_file if save_file is None else save_file
    with open(save_file, 'wb') as out_file:
      pickle.dump(self, out_file, pickle.HIGHEST_PROTOCOL) 
  
  def extrapolate_links_from_identifier(self, id_field='lobbyist_id'):
    graph = self.graph.copy()
    graph['lobbyist_legislator'] = [ ((lo,le) if not (pd.isna(lo) or pd.isna(le)) else None) \
                                              for lo, le in zip(graph[id_field], graph.legislator) ]
    lobbyist_id2legislators = graph[[id_field, 'legislator']].dropna().groupby(id_field).agg(set)
    lobbyist_id2lobbyist_legislators = graph[[id_field, 'lobbyist_legislator']].dropna().groupby(id_field).agg(set)
    lobbyist_id2client_names = graph[[id_field, 'client_name']].dropna().groupby(id_field).agg(set)
    client_name2lobbyists = graph[['client_name', id_field]].dropna().groupby('client_name').agg(set)
    client_name2legislators = graph[['client_name', 'legislator']].dropna().groupby('client_name').agg(set)
    client_name2lobbyist_legislators = graph[['client_name', 'lobbyist_legislator']].dropna().groupby('client_name').agg(set)
    
    # check for any  missing legislator links
    new_rows = { 'client_name': [], id_field: [], 'covered_position': [], 'legislator': [] }
    for row in tqdm(client_name2lobbyist_legislators.reset_index().iloc, total=len(client_name2legislators)):
        client_name = row.client_name
        #legislators = row.legislator
        cs_lobbyist_legislators = row.lobbyist_legislator #client_name2lobbyist_legislators.loc[client_name]
        
        lobbyist_legislators = set()
        for (lobbyist, legislator) in cs_lobbyist_legislators:
            ls_legislators = lobbyist_id2lobbyist_legislators.loc[lobbyist].lobbyist_legislator
            #print(type(ls_legislators), ls_legislators)
            lobbyist_legislators.update(ls_legislators)
        
        missing_links = lobbyist_legislators.difference(cs_lobbyist_legislators)
        if len(missing_links) > 0:
            for lobbyist, legislator in missing_links:
                new_rows['client_name'].append(client_name)
                new_rows[id_field].append(lobbyist)
                new_rows['legislator'].append(legislator)
                position_documented = f'EXTRAPOLATED lobbyist={lobbyist} linked to legislator=({legislator}) in a filing'
                new_rows['covered_position'].append(position_documented)
    new_rows = pd.DataFrame(new_rows)
    print(f'there are {len(new_rows)} extrapolated links to add')
    if len(new_rows) > 0:
        new_graph = pd.concat([self.graph.copy(), new_rows])
    else:
        new_graph = self.graph.copy()  
    return LobbyLinks(self.filing_data, graph=new_graph, legislators_handler=self.legislators)
  
  def visualize(self, outfile=None, drop_duplicates=True, weight_by_mass=True, \
                      height=None, width=None, group_by='client_name', 
                      client_weights=None, legislator_weights=None, 
                      only_current_legislators=False, 
                      client_hover_text=None, legislator_hover_text=None, 
                      #NEW: can pass a filter for an initial pass on the nodes, 
                      #     e.g. choose a center node [TESLA], and then get all
                      #     nodes within [filter_n_hops] hops of [TESLA]
                      #     [graph_filter] should be a boolean function returning
                      #     a boolean array used to filter the stored graph
                      graph_filter=None, filter_n_hops=1, 
                      font_size=12):
    #client_weights: a dictionary with client names to values 
    #	which will be logarithmically rescaled to yield node sizes
    graph = self.graph.copy()
    assert group_by in graph.keys()
    if height is None: height = '750px'
    if width is None: width = '1500px'
    if drop_duplicates:	#optionally drop duplicate links
      #graph = graph.drop_duplicates(subset=['client_name', \
      #                                      'legislator', \
      #                                      'edge_type'])
      group_agg_by = ['client_name', 'legislator', 'edge_type', 
                      'party', 'title', 'currently_in_office']
      agg_as = { 'contract_value': np.sum }
      for k in set([ k_ for k_ in graph.keys() if (k_ not in group_agg_by \
                                               and k_ not in agg_as) ]):
        agg_as[k] = lambda x: list(set(x))
      graph = graph.groupby(group_agg_by).agg(agg_as).reset_index()
    
    if only_current_legislators:
      graph = graph[graph.currently_in_office.astype(bool)]
    
    #filter graph
    if graph_filter is not None:
      graph_ = graph[graph_filter(graph)]
      #if filter_n_hops > 1:
      for hop in range(filter_n_hops-1):
        current_client_nodes = graph_.client_name.unique()
        current_leg_nodes = graph_.legislator.unique()
        ###get the list of all current nodes
        #
        relevant_entries = np.logical_or(
                                np.isin(graph.client_name, current_client_nodes), 
                                np.isin(graph.legislator, current_leg_nodes) )
        graph_ = pd.concat([graph_, graph[relevant_entries]])
        if drop_duplicates:
          group_by = ['client_name', 'legislator', 'edge_type', 
                      'title', 'party', 'currently_in_office']
          agg_as = { 'contract_value': np.sum }
          for k in set([ k_ for k_ in graph.keys() if k_ not in group_by and k_ not in agg_as ]):
            agg_as[k] = set
          graph_ = graph.groupby(group_by).agg(agg_as).reset_index()
        #graph_ = graph_.drop_duplicates(subset=['client_name', \
        #                                       'legislator', \
        #                                       'edge_type'])
      graph = graph_
    
    print('graph shape', graph.shape)
    #graph_summed = graph.groupby(['legislator', 'edge_type', \
    #                              group_by, 'currently_in_office', \
    #                              'title' ]).sum().reset_index()
    G = nx.from_pandas_edgelist(graph, source=group_by, \
                                target='legislator', edge_attr='confidence')
    graph_viz_net = Network(height, width, notebook=True, directed=False)
    graph_viz_net.from_nx(G)
    
    print('graph_viz_net', graph_viz_net)
    
    #aesthetic touches
    client_counts = graph[group_by].value_counts() #count of edges from each client
    legislator_counts = graph.legislator.value_counts()
    if legislator_weights is None:
      leg_node_weights = 1 + np.log(legislator_counts)
    else:
      weight_vals = np.array(list(legislator_weights.values()))
      interval = weight_vals.max() - weight_vals.min()
      rescale = lambda x: 1 + np.log(1 + 2*(x - \
                          max(0,weight_vals.min()))/interval* \
                          max(client_counts.max(), legislator_counts.max()))
      leg_node_weights = { legislator: rescale(val) for \
                              legislator, val in legislator_weights.items() }
    
    if client_weights is None:
      _client_weights = client_counts
      #client_node_weights = 1 + np.log(client_counts)
      client_node_weights = 1 + np.log(_client_weights)
    else:
      #rescale weights to match sizes of nodes in the edge-count case
      #client_weights = pd.DataFrame(np.array(client_weights.values()
      weight_vals = np.array(list(client_weights.values()))
      interval = weight_vals.max() - weight_vals.min()
      rescale = lambda x: 1 + np.log(1 + 2*(x - \
                          max(0,weight_vals.min()))/interval* \
                          max(client_counts.max(), legislator_counts.max()))
      client_node_weights = { client: rescale(val) for \
                              client, val in client_weights.items() }
    
    print(client_node_weights)
    #else:
    #  raise NotImplementedError()
    leg_party =     { leg: graph[graph.legislator == \
                      leg].party.value_counts().idxmax() \
                      for leg in graph.legislator.unique() }
    leg_in_office = { leg: graph[graph.legislator == \
                      leg].currently_in_office.value_counts().idxmax() \
                      for leg in graph.legislator.unique() }
    for node in graph_viz_net.nodes:
      try:
        node['mass'] = float(client_node_weights[node['label']])**2
        node['color'] = 'purple'
        node['size'] = float(client_node_weights[node['label']])*10
        node['font_size'] = font_size
        #node['shape'] = 'triangle'
        if client_hover_text is not None:
          try: node['title'] = client_hover_text[node['label']]
          except KeyError: pass
      except KeyError:
        color = 'blue' if leg_party[node['label']] == 'Democrat' else \
               ('red' if leg_party[node['label']] == 'Republican' else 'green')
        node['mass'] = float(leg_node_weights[node['label']])**2
        node['color'] = color
        node['size'] = float(leg_node_weights[node['label']])*10
        node['font_size'] = font_size
        if legislator_hover_text is not None:
          node['title'] = legislator_hover_text[node['label']]
        if leg_in_office[node['label']] == 0.:
          node['shape'] = 'square'
      #node['label'] = '<b>'+node['label']+'</b>'
    graph_viz_net.inherit_edge_colors(False)
    #save the graph
    if outfile is not None: graph_viz_net.show(outfile)
    return graph_viz_net




