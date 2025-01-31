import signal
import inspect
from itertools import product
import re	#regular expression for string matching
from .resources.handlers import AttrDict
import string

strip_punct = lambda s: s.strip(string.punctuation)

class defaultValueDict(dict):
    def set_default(self,default_value):
        setattr(self,'default_value',default_value)
    def __missing__(self,key):
        return self.default_value


class TimeOutHandler(object):
  """Class to handle timeouts. Pass unexecuted function (e.g. 
  using func_ = lambda: func) to self.wrap(func_) to
  have function timeout after self.timeout seconds.
  kwarg:
  \ttimeout (in seconds)"""
  def __init__(self, timeout=10):
    self.timeout = timeout
  def handler(self, signum, frame):
    raise Exception('Timed Out')
  def wrap(self, func):
    def handler(signum, frame):
      raise Exception('Timed Out')
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(10)
    try:
      output = func()
      signal.alarm(0)
      return output
    except Exception as exc:
      signal.alarm(0)
      return #'timed out'

class DummyTimeout(object):
  def wrap(self, f):
    return f()

def varname(var):
  """
  Gets the name of var. Does it from the out most frame inner-wards.
  :param var: variable to get name from.
  :return: string
  """
  for fi in reversed(inspect.stack()):
    names = [var_name for var_name, var_val in fi.frame.f_locals.items() if var_val is var]
    if len(names) > 0:
      return names[0]

def build_queries(q_args):
  """Function to take queries (dict) with lists of LDA database keywords
  and returns a set of query dictionaries with the cross product of
  any keywords that are iterables."""
  #handle filing years as intervals
  fy = 'filing_year'
  if fy in q_args and type(q_args[fy]) in [tuple, list]:
    q_args[fy] = list(range(min(q_args[fy]), max(q_args[fy])+1))
  
  #extract iterable query terms:
  iter_args = [ (key, vals) for key, vals in q_args.items() 
                            if type(vals) in [tuple, list] ]
  iter_products = product(*[ vals for key, vals in iter_args])
  q_dicts = []
  for prod in iter_products:
    q = q_args.copy()
    for (key, vals), val in zip(iter_args, prod):
      q[key] = val
    q_dicts.append(q)
  return q_dicts

def _find_exact_searches(str_):
  #assert type(str_) == str
  str_ = str(str_)
  out = []
  in_exact = False
  for s in str_:
    if s == "\"":
      if not in_exact: 
        new_search = ''
        in_exact = True
      else: 
        out.append(new_search); in_exact = False
    else:
      if in_exact:
        new_search += s
      else: pass
  return out

def exact_search_filter(q_args):
  """Function that builds a filter for exact searches for substrings prefixed with
  \"[STR]\" as a post-processing step to LobbyData queries."""
  filters = { key: _find_exact_searches(val) for 
                   key, val in q_args.items() }
  filters = { key: searches for key, searches in \
                   filters.items() if len(searches) > 0 }
  def exact_search(filing):
    for key, searches in filters.items():
      try: 
        match_ = all( re.search(s.lower(), filing[key].lower()) for s in searches)
        #print(filing[key], searches, match_)
        if not match_: return False
      except KeyError:
        #try the next search term down the hierarchy
        key1, key2 = key.split('_', 1)
        try: 
          match_ = all( re.search(s.lower(), filing[key1][key2].lower()) 
                                                    for s in searches)
          #print(filing[key1][key2], searches, match_)
          if not match_:
            return False
        except KeyError: pass
    return True
  return exact_search

def _is_initials(name):
  #detect strings prefixed with initials, which
  #fuzzy name matching fails on
  nsplit = name.split()
  initials_re = '([A-Z]\.)+ '
  if len(nsplit) > 0:
   return re.match(initials_re, nsplit[0])

def _has_roman_suffix(name):
  #detect strings prefixed with initials, which
  #fuzzy name matching fails on
  nsplit = name.split()
  romans_re = '(([IXV]\.){1,4}|([IXV]){1,4})'
  if len(nsplit) > 0:
   return re.match(romans_re, nsplit[-1])


def _has_numerical_suffix(name):
  #detects strings suffixed with year suffix
  #(e.g. Sanders 1991-2002), which fuzzy
  #name matching fails on
  nsplit = name.split()
  suffix_re = '[0-9]'
  dash_re = '\-'
  if len(nsplit) > 0:
    if re.match(suffix_re, nsplit[-1]) or re.match(dash_re, nsplit[-1]):
      return True

def proc_name(name, length):
  #stacks several functions to fix commons errors in NER outputs
  no_errors = False
  
  while _has_numerical_suffix(name):
    try: #sometimes NER retains numerical suffixes (e.g. 19xx-20xx)
      name = name.split(maxsplit=1)[0]
      length = len(name.split())
    except IndexError: break
    
  while _is_initials(name):
    #recursively remove prefixes that are just initials
    #(which the fuzzy name matching fails on)
    #@ could add initials first letter match to legislator name
    try:	#sometimes the entire name is initials
      name = name.split(maxsplit=1)[1]
      length = len(name.split())
    except IndexError: break
  
  while _has_roman_suffix(name):
    try:
      name = name[::-1].split(maxsplit=1)[1][::-1]
      length = len(name.split())
    except IndexError: break
  name = strip_punct(name).strip()
  return name, length


def fuzzy_company_match(company_list):
  #builds a matrix of similarity values for a list of company names
  #using exact-match heuristics and fuzzywuzzy utilities
  import fuzzywuzzy
  #@@@@@@@@@@@@@@@@@@@@@@@@@@@@ NEXT EXPANSION @@@@@@@@@@@@@@@@@@



def get_filing_summary(filing):
  assert type(filing) == AttrDict
  summary_data = {}
  income = float(filing.income) if filing.income is not None else 0
  expenses = float(filing.expenses) if filing.expenses is not None else 0
  total_spend = income + expenses
  filing_period_ = filing.filing_period
  filing_period = ('Q1' if filing_period_ == 'first_quarter' else \
                  ('Q2' if filing_period_ in ('second_quarter', 'mid_year') else \
                  ('Q3' if filing_period_ == 'third_quarter' else \
                  ('Q4' if filing_period_ in ('fourth_quarter', 'year_end') else \
                                             filing.filing_period))))
  
  summary_data['registrant_id'] = filing.registrant.id
  summary_data['filing_year'] = (filing.filing_year)
  summary_data['client'] = (filing.client.name)
  if 'name__merged_from_' in filing.client.keys():
      summary_data['client_name_merged_from_'] = filing.client.name__merged_from_
  
  summary_data['client_industry'] = (filing.client.general_description)
  summary_data['lobbyist_income'] = (income)
  summary_data['lobbyist_expenses'] = (expenses)
  summary_data['total_spend'] = (total_spend)
  summary_data['lobby_entity'] = (filing.registrant.name)
  summary_data['filing_period'] = (filing_period)
  summary_data['year_and_period'] = '%i (%s)' % (filing.filing_year, \
                                                 filing_period)
  summary_data['filing_type'] = (filing.filing_type_display)
  summary_data['filing_id'] = (filing.filing_uuid)
  return summary_data

def get_activity_summary(activity):
  assert type(activity) == AttrDict
  summary_data = {}
  #target_keys: 'general_issue_code', 'general_issue_code_display', 
  #             'government_entities', 'foreign_entity_issues', 
  #             'description', 'num_lobbyists', 'government_entities'
  n_lobbyists = len(activity.lobbyists)
  govt_entities = tuple( entity.name for entity in activity.government_entities )
  summary_data['general_issue_code'] = activity.general_issue_code
  summary_data['general_issue'] = activity.general_issue_code_display
  summary_data['foreign_entity_issues'] = activity.foreign_entity_issues
  summary_data['description'] = activity.description
  summary_data['num_lobbyists'] = n_lobbyists
  summary_data['government_entities'] = govt_entities
  return summary_data


def get_feca_filing_summary(filing):
  assert type(filing) == AttrDict
  summary_data = {}
  #income = float(filing.income) if filing.income is not None else 0
  #expenses = float(filing.expenses) if filing.expenses is not None else 0
  #total_spend = income + expenses
  filing_period_ = filing.filing_period
  
  contribution_amounts = [ float(contribution.amount) for \
                                 contribution in filing.contribution_items ]
  
  filing_period = ('Q2' if filing_period_ == 'mid_year' else \
                   ('Q4' if filing_period_ == 'year_end' else None) )
  summary_data['registrant_id'] = filing.registrant.id
  summary_data['total_spend'] = sum(contribution_amounts)
  summary_data['filing_year'] = (filing.filing_year)
  summary_data['filing_period'] = filing_period
  summary_data['year_and_period'] = '%i (%s)' % (filing.filing_year, \
                                                 filing_period )
  
  summary_data['registrant'] = (filing.registrant.name)
  summary_data['registrant_industry'] = (filing.registrant.description)
  summary_data['PACs'] = tuple(filing.pacs)
  
  #summary_data['lobby_entity'] = (filing.registrant.name)
  summary_data['filing_period'] = (filing_period_)
  summary_data['filing_type'] = (filing.filing_type_display)
  summary_data['filing_id'] = (filing.filing_uuid)
  return summary_data


def get_contribution_summary(contribution):
  assert type(contribution) == AttrDict
  summary_data = {}
  summary_data['contribution_type_'] = contribution.contribution_type
  summary_data['contribution_type'] = contribution.contribution_type_display
  summary_data['contributor'] = contribution.contributor_name
  summary_data['recipient'] = contribution.payee_name
  summary_data['honoree'] = contribution.honoree_name
  summary_data['amount'] = float(contribution.amount)
  summary_data['date'] = contribution.date
  return summary_data







