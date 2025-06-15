from collections import defaultdict
import json
import re

# 1. Data preparation
def json_to_corpus(json_data):
    text = []
    volcano = json_data
    text.append(f"Volcano: {volcano['name']}")
    if volcano['alternate_names']:
        text.append(f"Synonyms: {', '.join(volcano['alternate_names'])}")
    text.append(f"Location: {volcano['location']['country']}, {volcano['location']['region']}, coordinates {volcano['location']['coordinates']}")
    text.append(f"Elevation: {volcano['elevation_m']} meters")
    text.append(f"Status: {volcano['status']}")
    text.append(f"Last Eruption: {volcano['last_known_eruption']}")
    for key, value in volcano['population'].items():
        text.append(f"Population {key}: {value}")
    text.append(f"Rock Types Major: {', '.join(volcano['rock_types']['major'])}")
    text.append(f"Rock Types Minor: {', '.join(volcano['rock_types']['minor'])}")
    text.append(f"Volcano Types: {', '.join(volcano['volcano_types'])}")
    for cone in volcano['features']['Cones']:
        elevation = cone['elevation'] if cone['elevation'] else 'unknown'
        text.append(f"Cone: {cone['name']}, type {cone['type']}, elevation {elevation}")
    for crater in volcano['features']['Craters']:
        text.append(f"Crater: {crater['name']}, type {crater['type']}")
    for period in volcano['eruption_history']:
        date_range = period['period']['date_range']
        eruption_type = period['period']['eruption_type']
        vei = period['period']['vei']
        impact = period['impact'] or 'none'
        text.append(f"Eruption: {date_range}, type {eruption_type}, VEI {vei}, impact {impact}")
    text.append(f"Summary: {volcano['summary']}")
    return "\n".join(text)

with open("../dataset/volcanoes.json", 'r') as f:
    file = json.loads(f)

json_data = file
corpus = json_to_corpus(json_data)
with open("adams_corpus.txt", "w", encoding="utf-8") as f:
    f.write(corpus)

# 2. Tokenization
def get_stats(vocab):
    pairs = defaultdict(int)
    for word, freq in vocab.items():
        symbols = word.split()
        for i in range(len(symbols)-1):
            pairs[(symbols[i], symbols[i+1])] += freq
    return pairs

def merge_vocab(pair, vocab):
    new_vocab = {}
    bigram = ' '.join(pair)
    replacement = ''.join(pair)
    for word in vocab:
        new_word = word.replace(bigram, replacement)
        new_vocab[new_word] = vocab[word]
    return new_vocab

with open("adams_corpus.txt", "r", encoding="utf-8") as f:
    text = f.read()
words = re.findall(r'\w+|[^\w\s]', text, re.UNICODE)
vocab = defaultdict(int)
for word in words:
    vocab[' '.join(list(word))] += 1
num_merges = 500
for i in range(num_merges):
    pairs = get_stats(vocab)
    if not pairs:
        break
    best = max(pairs, key=pairs.get)
    vocab = merge_vocab(best, vocab)
tokens = set(' '.join(vocab.keys()).split())
token_to_id = {token: idx for idx, token in enumerate(tokens)}
token_to_id['<unk>'] = len(token_to_id)
token_to_id['<pad>'] = len(token_to_id)
token_to_id['<bos>'] = len(token_to_id)
token_to_id['<eos>'] = len(token_to_id)
id_to_token = {idx: token for token, idx in token_to_id.items()}

with open("vocab.json", "w") as f:
    json.dump(token_to_id, f)

def encode(text):
    words = re.findall(r'\w+|[^\w\s]', text, re.UNICODE)
    tokens = []
    for word in words:
        word = ''.join(word)
        while len(word) > 0:
            for i in range(len(word), -1, -1):
                subword = word[:i]
                if subword in token_to_id:
                    tokens.append(token_to_id[subword])
                    word = word[i:]
                    break
            else:
                tokens.append(token_to_id['<unk>'])
                word = word[1:]
    return tokens
