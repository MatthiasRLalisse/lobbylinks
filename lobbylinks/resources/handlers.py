#classes to handle resources in this directory
#resources: 	ontology of legislators
#		LDA issue code names & map to human-readable

#basic imports
import signal
import os
import json
import re
from collections import defaultdict
from .match_heuristics import whittle_name, patterns, \
                              top_level_patterns
from datetime import datetime
from .name_matcher import NameMatcher
from . import probablepeople_mod as pp
from .nicknames import NickNamer

from unidecode import unidecode

#minimize tensorflow printouts
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # or any {'0', '1', '2'}

#numerical computing imports
import pandas as pd
import numpy as np

#nlp imports
import spacy
from . import hmni #lstm-based fuzzy name matching

_lower = lambda l: [ unidecode(s.lower()) for s in l ]

try:
  ml_matcher = hmni.Matcher(model='latin', allow_alt_surname=False) #machine learning name matcher
  enable_matching = True
except:
  print('machine learning name-matching not enabled')
  ml_matcher = lambda x, y: 0.
  enable_matching = False


string_matcher = NameMatcher(distfun='jaro_winkler')
ml_matcher = ml_matcher
nicknamer = NickNamer()


#minimize tensorflow printouts
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # or any {'0', '1', '2'}

q_auth = ('MLalisse', 'LobbyLinks&') #credentials for database query

#utility to extract legislator name; used in Legislators obj
name_keys = ['first', 'middle', 'last']
namesort = lambda keys: sorted([k for k in keys if 
                        k in name_keys], key=lambda x: name_keys.index(x))

#utility to extract lobbyist name; used in LobbyLinks obj
lobby_name_keys = ['first_name', 'middle_name', 'last_name']
lobby_namesort = lambda keys: sorted([k for k in keys if 
                        k in lobby_name_keys], 
                        key=lambda x: lobby_name_keys.index(x))

#historical_leg_resource = os.path.join('lobbylinks', 'resources', 
#                                       'legislators-historical.json')
#current_leg_resource = os.path.join('lobbylinks', 'resources', 
#                                    'legislators-current.json')
#issue_codes_resource = os.path.join('lobbylinks', 'resources', 
#                                    'lda_issue_codes.csv')
import sys
path = os.path.dirname(os.path.abspath(__file__))

historical_leg_resource = os.path.join(path, 'legislators-historical.json')
current_leg_resource = os.path.join(path, 'legislators-current.json')
executives_resource = os.path.join(path, 'executive.json')
issue_codes_resource = os.path.join(path, 'lda_issue_codes.csv')
candidates_resource = os.path.join(path, 'candidates_1980-2022-named.csv')
crp2fec_id_resource = os.path.join(path, 'crp_cand_id_map.csv')
manual_id_resource = os.path.join(path, 'leg_ids_manual.csv')


#with open(historical_leg_resource, 'r') as f:
#  o = f.read()

#print(historical_leg_resource)

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


class AttrDict(dict):
  """OOP-friendly format for dictionaries. Values addressable with obj.key format"""
  def __init__(self, *args, recursive=True, **kwargs):
    super(AttrDict, self).__init__(*args, **kwargs)
    self.__dict__ = self
    if recursive:
      for key in self:
        if type(self[key]) == dict:
          self[key] = AttrDict(self[key])
        elif type(self[key]) in [list, tuple]:
          new_val = []
          for v in self[key]:
            try: new_val.append(AttrDict(v))
            except: new_val.append(v)
            self[key] = new_val
  def __setattr__(self, attr_name, val):
    self[attr_name] = val
    super(AttrDict, self).__setattr__(attr_name, val)


class IssueCodes(object):
  """dict-like object to map LDA issue codes to human-readable names"""
  def __init__(self, sourcefile=issue_codes_resource):
    codes_map = pd.read_csv(sourcefile)
    self.code2name = { code: name for code, name in zip(codes_map.issue_code, 
                                                        codes_map.issue_name) }
    self.name2code = { name: code for code, name in self.code2name.items() }
  
  def __getitem__(self, key):
    return self.code2name[key]
  
  def items(self):
    return self.code2name.items()
  
  def match_names(self, query, AND=True):
    #matches a string with implied AND on all input terms by default
    #set AND=False if you want "or" results
    #uses bag of words (e.g. same matches for 'climate change' and 'change climate')
    query_terms = query.split()
    matches_by_term = []
    for w in query_terms:
      matches = [ code for code, issue in self.items() \
                       if re.search(w.lower(), issue.lower()) ]
      matches_by_term.append(set(matches))
    if AND:
      matches = set.intersection(*matches_by_term)
    else:
      matches = set.union(*matches_by_term)
    return set(matches)

# TODO first initial, hypenated last name
def proc_hyphens(s):
    delimiters = { '-', ' ' }
    s = s.strip('- ')
    splits_ = re.split(r'(-|\s)', s)
    # add n-length concatenates
    splits = []
    N = len(splits_)
    for j in range(N):
        if splits_[j] not in delimiters:
            splits.append(splits_[j])
            for i in range(j+1, N):
              if splits_[i] not in delimiters:
                  s_ = ''.join(splits_[j:i+1])
                  splits.append(s_)
    return list(set(splits))       

#proc_hyphens('ros-hilena morechai-johnson')
def match_nicknames(name, nicknamer, legislators_data):
    parse_ = pp.tag(name, type='person')[0]
    scores = [ ]
    last_name = parse_.get('Surname')
    first_name = parse_.get('GivenName')
    first_initial = parse_.get('FirstInitial')
    #if isinstance(last_name, str): last_name = unidecode(last_name.lower())
    if not (isinstance(last_name, str) and (isinstance(first_name, str) or \
                                            isinstance(first_initial, str))):
        return np.zeros(len(legislators_data))
    
    last_name = unidecode(last_name).lower()
    
    if isinstance(first_name, str):
        given_name = unidecode(first_name).lower()
        name_set = nicknamer.canonicals_of(given_name).union(nicknamer.nicknames_of(given_name))
        name_set = {given_name}.union(name_set)
        name_set = { n for n in name_set if len(n) >= 3 }
    else:
        name_set = set()
    
    #print(name_set)
    if isinstance(first_initial, str):
        first_initial = unidecode(first_initial).lower()[0]
    
    for l in legislators_data:
        found_match = False
        try:
            leg_lastname = l.name.last
            leg_firstname = l.name.first
            # compile hyphenated last names
            #found_match = False
            
            if not (isinstance(leg_lastname, str) and isinstance(leg_firstname, str)):
                #scores.append(0.)
                continue
            
            leg_lastname_ = unidecode(leg_lastname).lower()
            leg_firstname = unidecode(leg_firstname).lower()
            leg_lastnames = proc_hyphens(leg_lastname_)
            for leg_lastname in leg_lastnames:
                if last_name != leg_lastname:
                    continue
                
                if isinstance(first_name, str):
                    leg_set = nicknamer.canonicals_of(leg_firstname \
                                      ).union(nicknamer.nicknames_of(leg_firstname))
                    leg_set = {leg_firstname}.union(leg_set)
                    leg_set = { n for n in leg_set if len(n) >= 3 }
                    if len(leg_set.intersection(name_set)) >= 1:
                        #scores.append(1.)
                        #print('othermatch', leg_set, leg_firstname, leg_lastnames)
                        found_match = True
                        #print(leg_set)
                        break
                if isinstance(first_initial, str):
                    leg_first_initial = leg_firstname[0]
                    if leg_first_initial == first_initial:
                        print('matched on initials', leg_first_initial, first_initial, leg_lastname, leg_firstname, last_name)
                        #print('using initials')
                        found_match = True
                        break
            if found_match: 
                #print('appending match', leg_firstname, leg_lastname, first_name, first_initial)
                scores.append(1.)
            else: scores.append(0.)
            #print('found match?', found_match)
        except AttributeError:
            print('attrerror')
            scores.append(0.)
    scores = np.array(scores)
    #print('nicknamer match', legislators_data[scores.argmax()])
    if scores.sum() > 0.:
        return scores/scores.sum()
    else:
        return scores

#match_nicknames('Thomas Cotton', legislators)
#match_nicknames('T. Cotton', legislators)

class Legislators(object):
  """list-like object to handle legislator names, parties, details, etc\n
  by default, merges current legislators and historical legislators, house & senate"""
  def __init__(self, sourcefiles= \
                     [ historical_leg_resource, 
                       current_leg_resource ], 
                     load_executive=True,
                     min_year=1990, 
                     max_year=9999, 
                     _filter=lambda l: True, 
                     enable_matching=True,
                     validate_cand_ids=False, # for devs, when updating IDs in the CAND_ID system for linking to FEC identifiers
                     ):
    if type(sourcefiles) == str: sourcefiles = [ sourcefiles ]
    self.min_year = str(min_year)
    self.max_year = str(max_year)
    #self.string_matcher = NameMatcher(distfun='jaro_winkler')
    #self.ml_matcher = ml_matcher
    #self.nicknamer = NickNamer()
    data = []
    for sourcefile in sourcefiles:
      with open(sourcefile, 'r') as f:
        leg_data = json.load(f)
        #when using the default resource files, tag with currently_in_office
        for legislator in leg_data:
          in_office = ('True' if sourcefile == current_leg_resource \
                      else ('False' if sourcefile == historical_leg_resource else 'Unk'))
          legislator['currently_in_office'] = in_office
        data += leg_data
    # filter for legislators in office after min_year
    legislators = [ AttrDict(entry) for entry in data if any( \
                                    [ term['end'] >= self.min_year 
                                    for term in entry['terms'] ]) \
                                    and any( [ term['start'] <= self.max_year \
                                    for term in entry['terms'] ]) ]
    for i, leg in enumerate(legislators): leg['index'] = i
    
    self.legislators = [ legislator for legislator in legislators if _filter(legislator) ]
    
    # add executive
    if load_executive:
      with open(executives_resource, 'r') as f:
        exec_data = json.load(f)
      
      # filter for executives in office after min_year
      executives = [ AttrDict(entry) for entry in exec_data if any( \
                                      [ term['end'] >= self.min_year 
                                      for term in entry['terms'] ]) \
                                      and any( [ term['start'] <= self.max_year \
                                      for term in entry['terms'] ]) ]
      for i, exec_ in enumerate(executives): exec_['index'] = i
      
      today = str(datetime.today().date())
      for i, exec_ in enumerate(executives):
          max_term = max( [ term['end'] for term in exec_['terms'] ] )
          exec_['currently_in_office'] = 'True' if max_term >= today else 'False'
      
      self.executives  = [ executive for executive in executives if _filter(executive) ]
    
    # add FEC IDs from the CRP id map
    df_crp_map = pd.read_csv(crp2fec_id_resource)
    crp_id2fec_ids = defaultdict(set)
    for crpid, fecid in zip(df_crp_map.CID, df_crp_map.FECCandID):
      crp_id2fec_ids[crpid].add(fecid)
    
    crp_id2fec_ids = { crp_id: list(fec_ids) for crp_id, fec_ids in crp_id2fec_ids.items() }
    
    # annotate with FEC-aligned candidate IDs
    df_candidates = pd.read_csv(candidates_resource)
    
    fecid2merged_id = { fecid: merged_id for fecid, merged_id \
                        in zip(df_candidates.CAND_ID, df_candidates.CAND_ID_MERGED) }
    
    # load manual spot checks
    df_manual = pd.read_csv(manual_id_resource, dtype=str)
    idtype_idval2new_idtype_new_idval = defaultdict(list)
    for (_,_,idtype, idval, newidtype, newidval) in df_manual.itertuples():
      idtype_idval2new_idtype_new_idval[(idtype, idval)].append((newidtype, newidval))
    #idtype_idval2newidtype_newidval = { (idtype, idval): (newidtype, newidval) for \
    #                                    (_,_,idtype, idval, newidtype, newidval) in df_manual.itertuples() }
    idtype_idval2new_idtype_new_idval = dict(idtype_idval2new_idtype_new_idval)
    
    self._dataiter_ = self.legislators
    if load_executive:
      self._dataiter_ += self.executives
    
    for leg in self:
      if 'fec' not in leg.id:
        try:
          crp_id = leg.id['opensecrets']
          fec_ids = crp_id2fec_ids[crp_id]
          leg.id['fec'] = fec_ids
        except KeyError:
          pass
      if 'fec' in leg.id:
        # map FECIDs to cand IDs
        cand_ids = sorted(list(set([ fecid2merged_id[s] for s in leg.id.fec \
                                                    if s in fecid2merged_id ])))
        leg.id['CAND_ID'] = cand_ids
        if validate_cand_ids:
            if len(cand_ids) > 1:
                print(f'found multiple candidate ID matches for {leg.name}: {cand_ids}')
                #except KeyError:
            elif len(cand_ids) < 1:
                print(f'missing candidate IDs for {leg.name}: {leg.id.fec}')
      
      new_entries = {}
      for idtype, idval in leg.id.items():
        try:
          new_id_vals = idtype_idval2new_idtype_new_idval[idtype, str(idval)]
          for newidtype, newidval in new_id_vals:
              if newidtype in leg.id:
                  #print(leg.id[newidtype])
                  if isinstance(leg.id[newidtype], (tuple, list)):
                      newidval = list(set(leg.id[newidtype]+[newidval]))
                  else:
                      newidval = list(set([leg.id[newidtype], newidval]))
                  #print(newidval)
              new_entries[newidtype] = newidval
              #newidtype, newidval = idtype_idval2newidtype_newidval[idtype, str(idval)]
          #new_entries[newidtype] = newidval
        except (KeyError,TypeError):
          pass
      leg.id.update(new_entries)
      
      #create list of names for each legislator
      for legislator in self:
          legislator['full_name'] = ' '.join(legislator.name[k] 
                                        for k in namesort(legislator.name.keys()))
      
          #tag each legislator with 'was house rep' or 'was senate'
    for leg in self:
      leg['was_house'] = any( term.type == 'rep' for term in leg.terms )
      leg['was_senate'] = any( term.type == 'sen' for term in leg.terms )
      if load_executive:
          leg['was_exec'] = any( term.type in ['prez', 'viceprez'] for term in leg.terms )
      
      if leg.was_house:
        first_house_start = min([ term.start for term in leg.terms if term.type == 'rep' ])
        leg['first_house_term_start'] = first_house_start
      if leg.was_senate:
        first_sen_start = min([ term.start for term in leg.terms if term.type == 'sen' ])
        leg['first_sen_term_start'] = first_sen_start
      
      if load_executive:
        if leg.was_exec:
          first_exec_start = min([ term.start for term in leg.terms if term.type in ['prez', 'viceprez'] ])
          leg['first_exec_term_start'] = first_exec_start
      
      first_term_start = min([ term.start for term in leg.terms ])
      leg['first_term_start'] = first_term_start
      
      # obtain name parses
  
  @property
  def names(self):
    return [ legislator.full_name for legislator in self.legislators ]
  
  @property
  def full_names(self):
    return [ (legislator.name.official_full if hasattr(legislator.name, \
                            'official_full') else legislator.full_name) \
                                     for legislator in self.legislators ]
  
  @property
  def last_names(self):
    return [ legislator.name.last for legislator in self.legislators ]
  
  @property
  def wikinames(self):
    return [ re.sub(" [\(\[].*?[\)\]]$", "", legislator.id.wikipedia) if \
                            hasattr(legislator.id, 'wikipedia') else \
                            '' for legislator in self.legislators ]
  
  @property
  def start_years(self):
    start_date = [ leg.first_term_start for leg in self.legislators ]
    return [ int(start_date.split('-')[0]) for start_date in start_date ]
  
  @property
  def house_reps(self):
    return [ leg for leg in self.legislators if leg.was_house ]
  
  @property
  def senators(self):
    return [ leg for leg in self.legislators if leg.was_senate ]
  
  @property
  def house_rep_names(self):
    return [ legislator.full_name for legislator in self.house_reps ]
  
  @property
  def house_rep_last_names(self):
   return [ legislator.name.last for legislator in self.house_reps ]
  
  @property
  def house_rep_full_names(self):
    return [ (legislator.name.official_full if hasattr(legislator.name, \
                            'official_full') else legislator.full_name) \
                                      for legislator in self.house_reps ]
  
  @property
  def house_rep_start_years(self):
    start_date = [ leg.first_term_start for leg in self.house_reps ]
    return [ int(start_date.split('-')[0]) for start_date in start_date ]
  
  @property
  def senator_names(self):
    return [ legislator.full_name for legislator in self.senators ]
  
  @property
  def senator_last_names(self):
    return [ legislator.name.last for legislator in self.senators ]
  
  @property
  def senator_full_names(self):
    return [ (legislator.name.official_full if hasattr(legislator.name, \
                            'official_full') else legislator.full_name) \
                                        for legislator in self.senators ]
  
  @property
  def senator_start_years(self):
    start_date = [ leg.first_term_start for leg in self.senators ]
    return [ int(start_date.split('-')[0]) for start_date in start_date ]
  
  
  @property
  def house_rep_wikinames(self):
    return [ re.sub(" [\(\[].*?[\)\]]$", "", legislator.id.wikipedia) if \
                            hasattr(legislator.id, 'wikipedia') else \
                            '' for legislator in self.house_reps ]
  
  @property
  def senator_wikinames(self):
    return [ re.sub(" [\(\[].*?[\)\]]$", "", legislator.id.wikipedia) if \
                            hasattr(legislator.id, 'wikipedia') else \
                            '' for legislator in self.senators ]
  
  def __len__(self):
    return len(self.legislators)
  
  def __getitem__(self, i):
    return self._dataiter_[i]
  
  def summary(self):
    print('Legislators inventory\n' \
          'Start year:\t %s\n' \
          'Number of entries:\t%i' \
          % (self.min_year, len(self) ))
  
  def lookup_id(self, id_, id_field='icpsr'):
    matches = []
    for legislator in self:
      try:
        ids = legislator.id[id_field]
        is_match = (str(id_) in [ str(leg_id) for leg_id in ids ]) \
                                     if type(ids) in [tuple, list] \
                                     else str(id_) == str(ids)
        if is_match:
          matches.append(legislator)
      except KeyError: pass
    if len(matches) > 1: return tuple(matches)
    elif len(matches) == 1: return matches[0]
    else: return None
  
  def score_names(self, name, target_names=None, exact=False, score_func=None):
    target_names = self.names if target_names is None else target_names
    
    if score_func is None:
      score_func = ml_matcher.similarity if enable_matching else ml_matcher
    
    #try exact match
    scores = (name == np.array(target_names))
    
    #if multiple matches, use a uniform distribution (won't meet match threshold)
    if np.any(scores): scores = scores/scores.sum()
    
    if ~np.any(scores) and not exact:
      #use name matcher to score all legislators with respect to a name tag
      #print(~np.any(scores), not exact, exact, 'using ml model')
      #assert hasattr(self, 'ml_matcher'), 'name matching not enabled'
      #if enable_matching:
      # strip any numbers, which messes w the algorithm
      name_ = re.sub(r'[0-9]', '', name)
      scores = [ score_func(name_, leg_name) \
                                 for leg_name in target_names ]
    
    scores = np.array(scores).astype(float)
    #softmax to take into account possible uniform distributions (multimatch)
    #scores = np.exp(scores)/np.exp(scores).sum()
    return scores
  
  def best_match(self, name, branch=None, last_name=False,
                       verbose=False, return_score=False, 
                       filing_year=None, allow_string_matches=True):
    
    if isinstance(branch, str):
        if branch.lower() in {'house', 'rep.', 'rep'}:
            branch = 'Rep'
        elif branch.lower() in {'senate', 'sen', 'sen.'}:
            branch = 'Sen'
        #print('branch:', branch)
        #assert branch in { 'Rep', 'Sen' }, \
        #  'Invalid value for branch. Set to `Rep` for House members, `Sen` for Senate.'
    
    #get best matching legislator for a name
    if last_name:
      names = _lower(self.house_rep_last_names) if branch == 'Rep' else \
                  (_lower(self.senator_last_names) if branch == 'Sen' else \
                 _lower(self.last_names))
    else:
      names = self.house_rep_names if branch == 'Rep' else \
                  (self.senator_names if branch == 'Sen' else \
                   self.names)
      full_names = self.house_rep_full_names if branch == 'Rep' else \
                  (self.senator_full_names if branch == 'Sen' else \
                   self.full_names)
      wiki_names = self.house_rep_wikinames if branch == 'Rep' else \
                  (self.senator_wikinames if branch == 'Sen' else \
                   self.wikinames)
    
    legislators = self.house_reps if branch == 'Rep' else \
                 (self.senators if branch == 'Sen' else \
                  self.legislators)
    
    leg_start_years = self.house_rep_start_years if branch == 'Rep' else \
                     (self.senator_start_years if branch == 'Sen' else \
                      self.start_years)
    # chronological filter ensuring that legislator had 
    #		       been in office before filing year
    if filing_year is None: year_is_valid = np.ones(len(leg_start_years))
    else: year_is_valid = filing_year >= np.array(leg_start_years)
    
    # control flow:
    # prefer HMNI (siamese network name-matcher) when a full name is provided
    # default to string-distance matchers ('jaro-winkler') if no match and allow_string_matches=True
    # if last name only, require exact match
    # if a chamber is provided ('Rep' or 'Sen'), the search is constrained to legislators from that chamber
    
    #Score names: 
    # if it's only a 1-word name (last_name=True), only use exact match
    # NB: the machine learning matcher requires first- and last-name for efficacy
    if last_name: 
      name = unidecode(name.lower())
      scores = self.score_names(name, target_names=names, exact=last_name)
    else:
      scores_all_names = [ self.score_names(name, target_names=names_list, \
                                                  exact=False) for names_list in \
                                                  [ names, full_names, wiki_names ] ]
      scores = np.max(np.vstack(scores_all_names), axis=0)
    
    scores = scores * year_is_valid 	# chronological filter
    
    #scores = self.score_names(name, target_names=names, exact=last_name)
    best_score = np.max(scores)
    best_match = legislators[np.argmax(scores)]
    
    if best_score > .7: #sets a threshold for name matches
      if return_score: 
        return best_match, best_score
      else:
        return best_match
    else:
      if last_name or not allow_string_matches:
        if verbose: print('no match')
        #print(best_score, scores)
        if return_score: return None, best_score
        else: return None
      else:
        if verbose: print('allowing string matches')
        # do same routine with a string-metric matcher
        score_func = lambda m, n: string_matcher.match_names(m, n, speed=None)
        scores_all_names = [ self.score_names(name, target_names=names_list, \
                                              exact=False, score_func=score_func) \
                                              for names_list in [ names, full_names, wiki_names ] ]
        scores = np.max(np.vstack(scores_all_names), axis=0)
        
        scores = scores * year_is_valid 	# chronological filter
        
        #scores = self.score_names(name, target_names=names, exact=last_name)
        best_score = np.max(scores)
        best_match = legislators[np.argmax(scores)]
        
       	#print(best_match, best_score)
        
        string_match_thresh = .92
        if best_score > string_match_thresh:
          if (scores > string_match_thresh).sum() > 1:
              print(f'{name}: there were multiple matches')
          if return_score: 
            return best_match, best_score
          else: 
            return best_match
        else:
          # try nicknames match
          nickname_scores = match_nicknames(name, nicknamer, legislators) * year_is_valid
          
          best_nickname_score = np.max(nickname_scores)
          best_match = legislators[np.argmax(nickname_scores)]
          
          if best_nickname_score > string_match_thresh:
              if return_score:
                  return best_match, best_nickname_score
              else:
                  return best_match
          else:
              if verbose: print('no match')
              if return_score: return None, best_score
              else: return None
      
      #if verbose: print('no match')
      #print(best_score, scores)
      #if return_score: return None, best_score
      #else: return None
    # DEPRECATED
    #else:
    #  #try using the official_full name
    #  if not last_name:
    #    scores = self.score_names(name, target_names=full_names, exact=False)
    #    best_score = np.max(scores)
    #    best_match = legislators[np.argmax(scores)]
    #    if best_score > .7:
    #      if return_score:
    #        return best_match, best_score
    #      else: 
    #        return best_match
    #    else:
    #      #try using the wikiname
    #      scores = self.score_names(name, target_names=wiki_names, exact=False)
    #      best_score = np.max(scores)
    #      best_match = legislators[np.argmax(scores)]
    #      if best_score > .7:
    #        if return_score:
    #          return best_match, best_score
    #        else:
    #          return best_match
    #      else:
    #        if verbose: print('no match')
    #        if return_score: return None, best_score
    #        else: return None
    #  else:
    #    if verbose: print('no match')
    #    if return_score: return None, best_score
    #    else: return None

class LegislatorExtractor(object):
  """Class to extract legislator names from free text."""
  def __init__(self, spacy_model="en_core_web_trf"): 
    #self.ninja = ninja_postproc
    self.nlp = spacy.load(spacy_model)
    self.rep_words = sorted([ 'Representative', 'Rep.', 'Rep',\
                              'Reps', 'Reps.', 
                              'Congressman', 'Congresswoman' \
                              'Congressperson', 'Cong', 'Cong.' ], key=len)[::-1]
    self.sen_words = sorted([ 'Senator', 'Sen', 'Sen.', 'Sens', \
                              'Senators', 'Sens.' ], key=len)[::-1]
    self.rep_words_ = [ t.lower() for t in self.rep_words ]
    self.sen_words_ = [ t.lower() for t in self.sen_words ]
    self.leg_words_ = self.rep_words_ + self.sen_words_
  def extract(self, sent, verbose=False):
    # proc text to catch common typos, such as parentheses adjacent to names
    sent = re.sub(r'(\S)(\(|\)|,|\!|\?|\;|\:)', r'\1 \2', sent)
    sent = re.sub(r'(\(|\)|,|\!|\?|\;|\:)(\S)', r'\1 \2', sent)
    sent = re.sub(r'([A-Za-z]+)?([0-9]+)', r'\1 \2', sent)
    sent = re.sub(r'([0-9]+)([A-Za-z]+)', r'\1 \2', sent)
    doc = self.nlp(sent)
    ents = doc.ents
    #match entities that fit the pattern [rep_word/sen_word] [person_tagged_word]+
    out = {}
    for e in doc.ents:
      #if entity is labeled as PERSON, extract possible legislator
      if e.label_ == 'PERSON':
        if verbose: print('extracting entity')
        title_ = doc[e.start-1].text #potential legislator title
        title2_ = doc[e.start].text #sometimes titles are chunked inside entity
        if title2_.lower() in self.leg_words_:
          title_ = title2_; e_ = e[1:]; e_text = e_.text
        else: e_text = e.text; e_ = e
        if title_.lower() in self.rep_words_: 
          out[e_text] = ('Rep', len(e_text.split()))
        elif title_.lower() in self.sen_words_:
          out[e_text] = ('Sen', len(e_text.split()))
        else:
          out[e_text] = ('Leg', len(e_text.split()))
        
        # sometimes the name is concatenated to the title
        matches_rep = [ title2_.lower().startswith(s) for s in self.rep_words_ ]
        matches_sen = [ title2_.lower().startswith(s) for s in self.sen_words_ ]
        if sum(matches_rep) > 0:
          title_ = self.rep_words_[np.argmax(matches_rep)]
          title_len_ = len(title_)
          e_text = e.text[title_len_:].strip()
          if e_text not in out and len(e_text) > 0:
            if title_[-1] in {'.', ','} or e_text[0] in {',', '.', ';'} or e_text[0].isupper():
              out[e_text] = ('Rep', len(e_text.split()))
        if sum(matches_sen) > 0:
          title_ = self.sen_words_[np.argmax(matches_sen)]
          title_len_ = len(title_)
          e_text = e.text[title_len_:].strip()
          if e_text not in out and len(e_text) > 0:
            if title_[-1] in {'.', ','} or e_text[0] in {',', '.', ';'} or e_text[0].isupper():
              out[e_text] = ('Sen', len(e_text.split()))
        
    if verbose: print(out, doc.text)
    return out

class CompanyMatcher(object):
  def __init__(self, top_lvl_patterns=top_level_patterns, \
                     patterns=patterns):
    self.top_lvl_patterns = top_lvl_patterns
    self.patterns = patterns
  def reduce(self, name):
    merged_name = whittle_name(name, \
                  top_level_patterns=self.top_lvl_patterns, \
                  patterns=self.patterns, return_shortest=True)
    return merged_name


