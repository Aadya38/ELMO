# -*- coding: utf-8 -*-
"""bilstm.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1OkHuoxsaGv_6rZ6n2g-QCed_V-FphyR-
"""

import pandas as pd
import numpy as np
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from collections import defaultdict
import torch
from torch.utils.data import Dataset, DataLoader
from nltk.tokenize import sent_tokenize, word_tokenize
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm
import random
import string
import string
import os
import torch.nn.functional as F
from torch.utils.data import Dataset
import matplotlib.pyplot as plt
from sklearn.metrics import f1_score, recall_score, precision_score, confusion_matrix
from nltk.tokenize import word_tokenize
nltk.download('punkt')
nltk.download('stopwords')

class preprocess_data():
    def __init__(self, file_path):
        self.filepath = file_path
        self.word2idx = {}
        self.idx2word = {}
        self.vocab = []
        self.vocab_size = 0

        self.words = []
        self.labels = []
        self.remove_words()

    def preprocess(self , data , stop_words , ps):
        data = " ".join(data)
        data = data.lower()
        data1 = [char if char not in string.punctuation else ' ' for char in data]
        pre_data = "".join(data1)
        words = pre_data.split()
        cleaned_string = ' '.join(words)

        return cleaned_string

    def remove_words(self):
        data_df = pd.read_csv(self.filepath)
        data = data_df['Description']
        data = data.tolist()

        labels = data_df['Class Index']
        labels = labels.tolist()

        stop_words = set(stopwords.words('english'))
        ps = PorterStemmer()

        preprocessed_sentences= []
        labels_encoded = []
        for sentence, label in tqdm(zip(data, labels)):
            sentence = sent_tokenize(sentence)
            sentence = self.preprocess(sentence, stop_words, ps)
            preprocessed_sentences.append(sentence)
            labels_encoded.append(label)

        self.words = preprocessed_sentences
        self.labels = labels_encoded

        word_freq = defaultdict(int)
        preprocessed_sentences = preprocessed_sentences[:20000]
        word2idx = {}
        idx2word = {}
        word2idx['<PAD>'] = 0
        word2idx['<UNK>'] = 1
        idx2word[0] = '<PAD>'
        idx2word[1] = '<UNK>'
        vocab = []
        vocab.append('<PAD>')
        vocab.append('<UNK>')
        vocab_size = 2
        for sentence in preprocessed_sentences :
            sentence = sentence.split()
            for word in sentence :
                word_freq[word] += 1

        for (word , freq) in (word_freq.items()):
            word2idx[word] = vocab_size
            idx2word[vocab_size] = word
            vocab.append(word)
            vocab_size+=1

        self.word2idx = word2idx
        self.idx2word = idx2word
        self.vocab = vocab
        self.vocab_size = vocab_size

dataset_model = preprocess_data('train.csv')

vocab = dataset_model.vocab
word2idx = dataset_model.word2idx
idx2word = dataset_model.idx2word
vocab_size = dataset_model.vocab_size

class CustomDataset(Dataset):
    def __init__(self, data, preprocess_data, max_len=None):
        self.preprocess_data = preprocess_data
        self.word2idx = self.preprocess_data.word2idx
        self.data = data
        self.max_len = max(len(word_tokenize(sent)) for sent in self.data['Description'])
        self.tokens = []
        self.labels = []
        for index, row in self.data.iterrows():
            sentence = row['Description']
            label = row['Class Index']
            tokens = self.padding(sentence)
            self.tokens.append(tokens)
            self.labels.append(label)

    def padding(self, sentence):
        words = word_tokenize(sentence)
        tokens = [self.word2idx[word] if word in self.word2idx else self.word2idx['<UNK>'] for word in words]
        if self.max_len is not None:
            tokens = tokens[:self.max_len] + [self.word2idx['<PAD>']] * (self.max_len - len(tokens))
        return tokens

    def __getitem__(self, index):
        tokens = self.tokens[index]
        label = self.labels[index]

        forward_data = tokens[1:]
        backward_data = tokens[:-1]
        return  torch.tensor(forward_data), torch.tensor(backward_data)

    def __len__(self):
        return len(self.data)

data1 = pd.read_csv('train.csv')
#Considered the top 20k sentences

data1 = data1[:20000]
train_dataset = CustomDataset(data1 , dataset_model)

val_data = pd.read_csv('train.csv')
val_data = val_data[20001:25001]
valid_dataset = CustomDataset(val_data , dataset_model)

test_data = pd.read_csv('test.csv')
test_dataset = CustomDataset(test_data , dataset_model)

from google.colab import drive

# Mount Google Drive
drive.mount('/content/drive')

# Path to the GloVe file in your Google Drive
glove_file_path = '/content/drive/My Drive/glove.6B.300d.txt'

glove_dict = {}
with open(glove_file_path, 'r', encoding='utf-8') as f:
    for line in f:
        tokens = line.strip().split(' ')
        word = tokens[0]
        embedding = np.array([float(val) for val in tokens[1:]])
        glove_dict[word] = embedding

UNK_emb = np.mean(list(glove_dict.values()), axis=0)
PAD_emb = np.zeros(300)

vocab = dataset_model.vocab
embeddings = []
for word in vocab:
    if word == '<UNK>':
        embeddings.append(UNK_emb)
    elif word == '<PAD>':
        embeddings.append(PAD_emb)
    elif word in glove_dict:
        embeddings.append(glove_dict[word])
    else:
        emb = np.random.uniform(-0.25, 0.25, 300)
        embeddings.append(emb)

embeddings = torch.tensor(embeddings, dtype=torch.float)

embedding = nn.Embedding.from_pretrained(embeddings, freeze=False, padding_idx=0)

print(embedding.weight.shape)

class elmo_model(nn.Module):
    def __init__(self, vocab_size, embedding, hidden_dim):
        super(elmo_model, self).__init__()
        self.vocab_size = vocab_size
        self.hidden_dim = hidden_dim
        self.embedding = embedding
        self.lstm1 = nn.LSTM(embedding.embedding_dim, hidden_dim,batch_first=True, bidirectional=True)
        self.lstm2 = nn.LSTM(hidden_dim*2, hidden_dim,batch_first=True, bidirectional=True)
        self.linear_out = nn.Linear(hidden_dim*2, vocab_size)

    def forward(self, back_data):
        back_embed = self.embedding(back_data)
        back_lstm1, _ = self.lstm1(back_embed)
        back_lstm2, _ = self.lstm2(back_lstm1)
        linear_out = self.linear_out(back_lstm2)
        return linear_out

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
VOCAB_SIZE = vocab_size
BATCH_SIZE = 64
EMBEDDING_DIM = 300
HIDDEN_DIM = 100

embedding = nn.Embedding.from_pretrained(embeddings, freeze=False, padding_idx=0)

elmo = elmo_model(VOCAB_SIZE, embedding, HIDDEN_DIM)
elmo.to(device)

train_dataloader = torch.utils.data.DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=False )

optimizer = optim.Adam(elmo.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss(ignore_index=0)

def train_elmo_model(epochs , data_loader , model , optimizer, criterion , device = device):
  for epoch in range(epochs):
    model.train()
    total_loss = 0
    iter = 0
    for (forward, backward) in tqdm(data_loader):
        forward = forward.to(device)
        backward = backward.to(device)
        optimizer.zero_grad()
        output = model(backward)
        loss = criterion(output.view(-1, VOCAB_SIZE), forward.view(-1))
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        iter += 1
    print(total_loss/len(data_loader))

  torch.save(model.state_dict() , 'bilstm.pt')

model_file = 'bilstm.pt'
if(os.path.exists(model_file)):
    elmo.load_state_dict(torch.load(model_file))
else:
    train_elmo_model(5 , train_dataloader , elmo , optimizer , criterion)

import matplotlib.pyplot as plt
from sklearn.metrics import f1_score, recall_score, precision_score, confusion_matrix

# Define a function to evaluate the model on a dataset and calculate metrics
def evaluate_model(model, data_loader, criterion, device=device):
    model.eval()
    total_loss = 0
    predictions = []
    targets = []

    with torch.no_grad():
        for (forward, backward) in data_loader:
            forward = forward.to(device)
            backward = backward.to(device)
            output = model(backward)
            loss = criterion(output.view(-1, VOCAB_SIZE), forward.view(-1))
            total_loss += loss.item()

            # Convert tensor predictions and targets to numpy arrays if they are not empty
            if forward.numel() > 0:
                predictions.extend(output.argmax(dim=-1).cpu().numpy().tolist())  # Convert to list
                targets.extend(forward.cpu().numpy().tolist())  # Convert to list

    avg_loss = total_loss / len(data_loader)

    # Calculate metrics only if targets and predictions are non-empty
    if targets and predictions:
        f1 = f1_score(np.array(targets), np.array(predictions), average='weighted')
        recall = recall_score(np.array(targets), np.array(predictions), average='weighted')
        precision = precision_score(np.array(targets), np.array(predictions), average='weighted')
        confusion = confusion_matrix(np.array(targets), np.array(predictions))
    else:
        f1, recall, precision, confusion = 0, 0, 0, []

    return avg_loss, f1, recall, precision, confusion

# Evaluate on validation and test datasets
val_loss, val_f1, val_recall, val_precision, val_confusion = evaluate_model(elmo, valid_dataset, criterion)
test_loss, test_f1, test_recall, test_precision, test_confusion = evaluate_model(elmo, test_dataset, criterion)

print("Validation Loss:", val_loss)
print("Validation F1 Score:", val_f1)
print("Validation Recall:", val_recall)
print("Validation Precision:", val_precision)
print("Validation Confusion Matrix:\n", val_confusion)

print("Test Loss:", test_loss)
print("Test F1 Score:", test_f1)
print("Test Recall:", test_recall)
print("Test Precision:", test_precision)
print("Test Confusion Matrix:\n", test_confusion)

# Plot Test and Validation Loss Graphs
epochs = range(1, 6)  # Assuming you trained for 5 epochs
val_losses = [val_loss] * len(epochs)  # Assuming you saved the validation loss after each epoch
test_losses = [test_loss] * len(epochs)  # Assuming you saved the test loss after each epoch

plt.figure(figsize=(10, 5))
plt.plot(epochs, val_losses, label='Validation Loss')
plt.plot(epochs, test_losses, label='Test Loss')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.title('Test and Validation Loss')
plt.legend()
plt.show()

embedding_file = 'elmo_embeds.pt'
if(os.path.exists(embedding_file)):
    elmo_embeddings = torch.load(embedding_file)
    print("EMBEDDINGS LOADED SUCCESSFULLY")
else:
    elmo_embeddings = list(elmo.parameters())[0].cpu().detach().numpy()

    torch.save(elmo_embeddings , 'elmo_embeds.pt')
    print("EMBEDDINGS SAVED SUCCESSFULLY")
print(elmo_embeddings.shape)