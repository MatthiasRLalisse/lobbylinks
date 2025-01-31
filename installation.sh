#!/bin/sh    
# preface installation with:
# >>> conda create --name lobbylinks python==3.7.9 -y && conda activate lobbylinks

# python dependencies
python -m pip install --upgrade pip

pip install -r ./requirements.txt
pip install safetensors==0.3.1
pip install scikit-learn==0.23.1 numpy==1.21.2 pandas==1.3.5 tensorflow protobuf==3.20.1 unidecode fuzzywuzzy abydos==0.5.0 joblib pywordsegment pluralizer spacy==3.6.1 nltk jellyfish==0.11.2 future probableparsing python-crfsuite wordfreq doublemetaphone networkx pyvis wordninja --force
pip install pywordsegment hmni

# spacy's NLP models are used for extracting the lobby network from covered_positions
python -m spacy download en_core_web_trf
python -m spacy download en_core_web_sm
python -m spacy download en_core_web_md


pip install locationtagger
python -c "import nltk; nltk.downloader.download('maxent_ne_chunker'); nltk.downloader.download('words'); nltk.downloader.download('treebank'); nltk.downloader.download('maxent_treebank_pos_tagger'); nltk.downloader.download('punkt'); nltk.download('averaged_perceptron_tagger')"

