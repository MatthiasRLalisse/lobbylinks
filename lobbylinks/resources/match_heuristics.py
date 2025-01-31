##################################################
######## COMPANY NAME MATCHING HEURISTICS ########
############# AND UTILITY CLASSES ################
##################################################

import re
import spacy
from pywordsegment import WordSegmenter as seg
from pluralizer import Pluralizer
import os.path as op
import os
import pandas as pd
from wordfreq import zipf_frequency
#from locationtagger import find_locations
import string

import sys
path = os.path.dirname(os.path.abspath(__file__))


punct_trans = str.maketrans(string.punctuation, ' '*len(string.punctuation))
strip_punct = lambda s: ' '.join(s.translate(punct_trans).split())

# import product category names
with open(op.join(path, 'product_category_names.txt'), 'r') as file:
  products = [ s.strip().upper().replace(' ', r'\s+') for s in file.readlines() if len(s.strip()) > 0 ] 

pluralizer = Pluralizer()
for product in set(products):
    products.append(pluralizer.pluralize(product))

products = sorted(list(set(products)), key=len)[::-1] # sort longest to shortest
product_regexes = [ re.compile(r'\b'+word+r'\b', re.IGNORECASE) for word in products ]

def extract_product(s):
  for regex in product_regexes:
      match = regex.search(s)
      if match is not None:
          prod = match[0]
          minus_prod = ' '.join(regex.sub(' ', s).split())
          if len(minus_prod) < 1:
              minus_prod = None
          return minus_prod, prod
  return s, None

_nlp = spacy.load('en_core_web_trf')

#	lightly preprocess by replacing dashes with spaces 
#	and removing extra whitespace
preproc = lambda s: ' '.join(s.replace('-', ' ').split()).replace('"', '')

#	expand certain abbreviations
abbreviations = [ (r'ASSOC(\.){0,1}(\b|$)', 'ASSOCIATION'), 
                  (r'ASSN(\.){0,1}(\b|$)', 'ASSOCIATION'), 
                  (r"ASS'N(\b|$)", 'ASSOCIATION'), 
                  (r'ASSOCS(\.){0,1}(\b|$)', 'ASSOCIATIONS'), 
                  (r'ASSNS(\.){0,1}(\b|$)', 'ASSOCIATIONS'), 
                  (r"ASS'NS(\.){0,1}(\b|$)", 'ASSOCIATIONS'), 
                  (r'SOC(\.){0,1}(\b|$)', 'SOCIETY'), 
                  (r'BROS(\.){0,1}(\b|$)', 'BROTHERS'), 
                  (r'CO(\.){0,1}(\b|$)', 'COMPANY'), 
                  (r'COMP(\.){0,1}(\b|$)', 'COMPANY'), 
                  (r'CMPNY(\.){0,1}(\b|$)', 'COMPANY'), 
                  (r'MFG(\.){0,1}(\b|$)', 'MANUFACTURING'), 
                  (r'MFRS(\.){0,1}(\b|$)', 'MANUFACTURERS'), 
                  (r'SVC(S{0,1})(\.){0,1}(\b|$)', 'SERVICES'), 
                  (r'SER(\.){0,1}(\b|$)', 'SERVICES'), 
                  (r"MGM('){0,1}T(\.){0,1}(\b|$)", 'MANAGEMENT'), 
              ] 
#		pre-compile to speed things up
abbreviations = [ (re.compile(regex, re.IGNORECASE), output) for regex, output in abbreviations ]
def expand_abbrevs(s):
  for abbrev, result in abbreviations:
    s = abbrev.sub(result, s)
  return s

#	basic query string for all regexes
base_string = '(.+?)(,){0,1}'

#	basic utilities for matching regexes
make_pattern = lambda regex: regex % base_string
getnames = lambda regex, target: re.search(make_pattern(regex), target, re.IGNORECASE)

# format for a pattern: tuple( PATTERN, GROUP )
#	GROUP is the index in the re.search call to retrieve
#PATTERNS with the target GROUP match (index to extract)
#	if prefixed w/ match, the pattern group is 2, else 1

#patterns that need to be searched first (with further processing after)
#if substrings match on this, send them down to the main patterns
top_level_patterns = [ 
            (r'^(.+) (\({0,1})ON BEHALF OF %s(\){0,1})$', 3), #JOHNSON (ON BEHALF OF GOLDMAN LLC)
            (r'^(.+) (\({0,1})O\.{0,1}B\.{0,1}O\.{0,1} %s(\){0,1})$', 3), #another way of writing ON BEHALF OF
            (r'^%s \({0,1}((FORMERLY)|((F|P)\.{0,1}K\.{0,1}A\.{0,1})|PREVIOUSLY)(\.,;:~)* (.)+\){0,1}$', 1), #X FORMERLY/PREVIOUSLY KNOWN AS
            (r'^%s \({0,1}((FORMERLY)|(PREVIOUSLY)) REPORTED AS (.)+\){0,1}$', 1), #X FORMERLY REPORTED AS 
            (r'^%s \({0,1}((AND)|&) (ITS ){0,1}(VARIOUS ){0,1}((SUBSIDIARIES)|(AFFILIATES))\){0,1}$', 1), #VERIZON & ITS VARIOUS SUBSIDIARIES
            (r'^%s \((.+)\)$', 3), #INTERNATIONAL BUSINESS MACHINES (IBM) / extract IBM from parenthesis
            (r'^(.+) \((?!((ON BEHALF OF)|(O\.{0,1}B\.{0,1}O{0,1}))\s+)%s\)$', 1), #IBM (INTERNATIONAL BUSINESS MACHINES) / extract IBM prefix
            (r'^\(.+\) %s$', 1), #(IBM) INTERNATIONAL BUSINESS MACHINES / extract INTERNATIONAL BUSINESS MACHINES
            (r'^THE %s$', 1), 
]


patterns = [
            (r'^%s(( )|(, ))INC(ORPORATED){0,1}(\.){0,1}', 1), # AMAZON INC.
            (r'^THE %s ((CORPORATION)|(CORP\.{0,1}))', 1), # THE AMAZON CORPORATION
            (r'^%s ((CORPORATION)|(CORP\.{0,1}))', 1), # AMAZON CORP.
            (r'^%s\.COM\b', 1), # AMAZON.COM
            (r'^%s COM\b', 1), # AMAZON COM
            (r'^%s ((LLC)|(L\.L\.C\.{0,1}))', 1), #ORIOLE CAPITAL GROUP LLC
            (r'^%s ((LLP)|(L\.L\.P\.{0,1}))', 1), #ACCENTURE LLP
            (r'^%s ((LP)|(L\.P\.{0,1}))', 1), #EXCELERATE ENERGY LP
            (r'^%s (L\.{0,1}T\.{0,1}D\.{0,1})', 1), #EXCELERATE ENERGY LP
            (r'^(THE )%s GROUP(,{0,1})', 1),	#THE GOLDMAN SACHS GROUP, INC. (recurse)
            (r'^%s STORES', 1), #WAL-MART STORES'
            (r'^(THE ){0,1}%s COMPANY', 2), #(THE )BOEING COMPANY
            (r'^%s CO(\.{0,1})', 1), #BOEING CO.
            (r'^%s,', 1), #cleans up e.g. GOOGLE,
            (r'^%s ((AND)|&) CO(\.|(MPANY)){0,1}', 1), #MCKINSEY & COMPANY
            (r'^%s \({0,1}HOLDINGS\){0,1}', 1), #MCKINSEY & COMPANY
            (r'^%s (?!((OF)|(FOR)) )((AMERICA)|((THE ){0,1}U\.{0,1}S\.{0,1}A\.{0,1}))$', 1), 
]

#	common product category & other suffixes, 
#	e.g. "MOTORS" (TESLA MOTORS), AMAZON CORPORATE...
prod_categories = ['MOTORS', 'FINANCIAL SERVICES', 'FUNDS SERVICES', \
            'CAPITAL MANAGEMENT', 'CAPITAL MANAGERS', 'CLIENT SERVICES', 
            'CARDS', 'NATIONAL', 'BANK', 'RAILROAD', 'RAILWAY', 'RAILWAYS', 
            'RAILWAY_OPERATORS', 'MOTOR VEHICLES', 
            'CONSULTING', 'CONSULTANTS', 'INDUSTRIES', 'SYSTEMS', 'MEDICAL SYSTEMS',
            'FUND', 'GOOD GOVERNMENT', 'RESTAURANTS', #'AMERICA', 
            'HOLDINGS', 'HOLDING COMPANIES', 'HOLDING COMPANY', 'RESOURCES', 
            'OIL', 'GAS', 'OIL & GAS', 'CAPITAL', 'FINANCIAL', 'INDUSTRIES', 
            'BROKERS', 'AGENTS', 'AGENTS & BROKERS', 'COUNCIL', 'BANCORP', 
            'BUILDERS', 'INTERNATIONAL', 'NATIONAL', 'USA', 'RAILPAC', 
            'SECURITIES', 'AND CO', 'AND CO.', 'NA', 'NORTH AMERICA',  
            'VENTURES', 'MANAGEMENT', 'CAPITAL', 'BANCORP', 'ENERGY',
            'LIFE INSURANCE', 'HEALTH INSURANCE', 'CASUALTY INSURANCE',
            'COMPANY', 'COMPANIES', 'HELICOPTERS', 'COMMUNICATIONS', 'GROUP', 
            'GROUP OF COMPANIES', 'SOLUTIONS'  ]

# revert to narrower suffix set
suffixes = ['MOTORS', 'FINANCIAL SERVICES', 'FUNDS SERVICES', \
            'CAPITAL MANAGEMENT', 'CLIENT SERVICES', 'PRODUCTION SERVICES', \
            'WEB SERVICES', 'SERVICES INC', 'SERVICES INC\.', 'CORPORATE', \
            'SERVICES COMPANY', 'SERVICES', 'CLIENT SERVICES', 'FEDERAL SERVICES', 
            'COMPANIES', 'COMPANY', 'CLIENT', 'NETWORKS', 'TECHNOLOGIES', 
            'OF AMERICA', 'PHARMACEUTICALS', 'PHARMACEUTICAL', 'HEALTH', 
            'INTERNATIONAL', 'PLATFORMS', 'SCIENCES', 'ANIMAL HEALTH', 
            'AEROSPACE', 'NATIONAL', 'OF THE UNITED STATES', 'ADVISORS', 
            'UNITED STATES', 'WEB SERVICES', 'SERVICES INC', r'SERVICES INC\.', 
            'CORPORATE', ' WEB', 'SERVICES', 
            'SERVICES COMPANY', 'SERVICES', 'CLIENT SERVICES', 'FEDERAL SERVICES',
            'NORTH AMERICA' ] # AMERICA but not OF AMERICA

suffixes = sorted(list(set(suffixes)), key=len)[::-1] # run longest first
for suffix in suffixes:
  patterns.append(('^%s '+suffix+'$', 1))

# product category patterns shouldn't be preceded by 'of'
for suffix in prod_categories:
  patterns.append((r'^%s\s+(?<!OF )'+suffix+'$', 1))

# ban items followed by 'on behalf of'
patterns_ = []
for pattern, index in patterns:
    if not pattern.endswith('$'):
        pattern += r'(?!\s*\({0,1}((O\.{0,1}B\.{0,1}O\.{0,1})|(ON BEHALF OF)))'
    patterns_.append((pattern, index))

patterns = patterns_

#	specific cases where the heuristics fail
#	format: tuple(boolean_function, value_if_true)
spot_checks = [ (lambda s: ('WAL-MART' in s or 'WALMART' in s \
                            or 'WAL MART' in s), 'WALMART'), 
                (lambda s: ('GOLDMAN SACHS' in s), 'GOLDMAN SACHS'), 
                (lambda s: ('KOCH ' in s), 'KOCH INDUSTRIES'), 
                (lambda s: ('VERIZON' in s), 'VERIZON'),
                (lambda s: (bool(re.match(\
                            '^((UNITED STATES)|(U(\.| ){0,1}S(\.| )' + \
                            '{0,1}(A(\.| ){0,1}){0,1}) )' + \
                            '(CHAMBER OF COMMERCE)$', s, re.IGNORECASE)) or \
                           bool(re.match(\
                            '^CHAMBER OF COMMERCE OF THE ' + \
                            '((UNITED STATES)|(U(\.| ){0,1}S(\.| )' + \
                            '{0,1}(A(\.| ){0,1}){0,1}))', s, re.IGNORECASE) )), \
                           'US CHAMBER OF COMMERCE'), \
                (lambda s: ('AT&T' in s), 'AT&T'), \
                (lambda s: re.search('T(-| )MOBILE', s, re.IGNORECASE), 'T-MOBILE'), 
                #(lambda s: ('AMAZON COM' in s), 'AMAZON'), # AMAZON tries to game the system
                (lambda s: ('ABBVIE INC' in s), 'ABBVIE'), #gets tripped up by the 
                                                           #TESLA MOTORS-->TESLA but 
                                                           #not GENERAL MOTORS-->GENERAL 
                                                           #heuristic
                (lambda s: re.search('(^|\W)GOOGLE(\W|$)', s), 'GOOGLE'), 
                (lambda s: s.strip().upper() == 'ALPHABET', 'GOOGLE'), 
                (lambda s: ('EXXON' in s), 'EXXON MOBIL'), 
                (lambda s: ('HYUNDAI' in s), 'HUNDAI'), 
                (lambda s: ('INTERNATIONAL BUSINESS MACHINES' in s), 'IBM'),
                (lambda s: ('BOEING' in s), 'BOEING'),
                (lambda s: ('COMCAST' in s), 'COMCAST'), 
                
]

df_states = pd.read_csv(op.join(path, 'state_abbreviations.csv'))
placenames = set()
for k in ['state', 'abbrev', 'code']:
    placenames.update(set(df_states[k].dropna().unique()))

with open(op.join(path, 'america_placenames.txt'), 'r') as file:
    placenames.update([ s.strip() for s in file.readlines() ])

placenames = frozenset([ strip_punct(s.upper()) for s in placenames ]) # block changes

#	main processing functions
def apply_pattern(pattern, group_id, name):
  match_result = getnames(pattern, name)
  if match_result is not None:
    try:
      result_str = match_result.group(group_id)
      result_str = result_str.strip()
      # strip any trailing punctuation
      result_str = result_str.strip(' &%*-.!-_+=,;:"\'').strip()
      # ensure result string is not a location name
      # (NEW YORK LIFE INSURANCE -/> NEW YORK
      if strip_punct(result_str.upper()) in placenames:
          return None
      else:
          return result_str
      #return result_str.strip()
    except IndexError:
      return None
  else: return None

def apply_patterns(patterns, name, recursive=False):
  new_names = set([name])
  for pattern, group_id in patterns:
    result = apply_pattern(pattern, group_id, name)
    if result is not None:
      new_names.add(result)
  #print(new_names)
  if recursive:
    if len(new_names) > 0:
      for name_ in new_names:
        new_names = new_names.union(apply_patterns(patterns, name_))
  return new_names

remove_names = { 'USA', 'US' }
fka = re.compile(r'^\s*((F\.{0,1}K\.{0,1}A\.{0,1})|(((FORMER(LY){0,1})|(PREVIOUSLY))(\s+KNOWN (AS)){0,1}))', re.IGNORECASE)
def filter_from_toplevel_(s):
    # filter certain common patterns
    if s.strip().startswith('(') and s.strip().endswith(')'):
        return False
    if fka.match(s):
        return False
    return True

endwith_of = re.compile(r'(^|\s)OF$', re.IGNORECASE)
def filter_endswith_of_(s):
    if endwith_of.search(s.strip()):
        return False
    return True

o_b_o = re.compile(r'^\s*((O\.{0,1}B\.{0,1}O\.{0,1})|(ON BEHALF OF))', re.IGNORECASE)
def filter_o_b_o_(s):
    if o_b_o.match(s): return False
    return True

terminal_filters = [ filter_endswith_of_, filter_o_b_o_ ]
def final_filter(s):
    return all( f(s) for f in terminal_filters )


#recursively apply patterns until names are cut down to minimum size
import string
punct_ = str.maketrans('', '', string.punctuation)
remove_punct = lambda s: s.translate(punct_)

strip_punct = lambda s: s.strip(' &%*-.!-_+=,;:"\'')
zipf_ = lambda s: zipf_frequency(strip_punct(s.split()[0]), 'en')

def whittle_name(name, top_level_patterns, patterns, return_shortest=True, word_segment=False):
  name = preproc(name)	# light preprocessing
  name = expand_abbrevs(name) # expand abbreviations
  
  #check if any of the spot checks apply
  if any( func(name) for func, out_name in spot_checks):
    valid_names = set([ out_name for func, out_name \
                                 in spot_checks if func(name) ])
  else:
    #apply top-level patterns
    names = apply_patterns(top_level_patterns, name, recursive=True)
    #print(0, names)
    names = { name for name in names if filter_from_toplevel_(name) }
    #print(1, names)
    #print('toplev', names)
    #print(names)
    #recursively extract names
    if len(names) == 0:
      names = apply_patterns(patterns, name, recursive=True)
    else:
      for name_ in names:
        names = names.union(apply_patterns(patterns, name_, recursive=True))
    
    #print(2, names)
    #filter names that are 1-word that is not a proper noun
    #	e.g. "TESLA MOTORS" should reduce to "TESLA" 
    #          but "GENERAL MOTORS" should not reduce to "GENERAL"
    valid_names = set()
    for name in names:
      if len(name.split()) > 1:
        valid_names.add(name)
      else:
        parse = _nlp(name.lower())
        if len(parse) >= 1:
            #print('checking tag', parse, parse[0].tag_, parse[0].tag_ in ['NNP'])
            # if word is a proper noun or very infrequent, accept
            if (parse[0].tag_ in ['NNP'] and zipf_(name) < 3.8) or\
               zipf_(name) < 1:
                valid_names.add(name)
    
    #valid_names = set([ name for name in names if (len(name.split()) > 1 \
    #                             or _nlp(name.lower())[0].tag_ in ['NNP']) ])
  
  #print(valid_names)
  
  if len(valid_names) == 0:
    valid_names = set([name])
  
  valid_names_ = { name for name in valid_names if strip_punct(name.upper()) \
                                                                        not in remove_names }
  if len(valid_names_) >= 1:
    valid_names = valid_names_
  valid_names_ = { name for name in valid_names if len(name) >= 4 }
  if len(valid_names_) >= 1:
     valid_names = valid_names_
  
  if word_segment: # experimental feature: add word segmentation
    seg_names = { ' '.join(seg.segment(name)) for name in valid_names }
    valid_names = valid_names.union(seg_names)
  
  valid_names = { name for name in valid_names if final_filter(name) }
  
  # remove punctuation
  valid_names = { strip_punct(name) for name in valid_names }
  
  if len(valid_names) == 0: return name
  
  #return the shortest result
  if return_shortest:
    return min(valid_names, key=lambda s: len(s))
  else:
    return valid_names



