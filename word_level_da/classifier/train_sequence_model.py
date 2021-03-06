"""Module to train sequence model.

https://www.tensorflow.org/tutorials/structured_data/imbalanced_data

"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import fasttext.util
import gc
import tensorflow as tf
import numpy as np
import random as rn
import os
import math
import pandas as pd
from collections import Counter
from word_level_da.classifier.build_model import rnn_model_fixed, cnn_model
from word_level_da.classifier.vectorize_data import vectorize
from word_level_da.classifier import scores
from word_level_da.preprocessing.process_data import ProcessData


class seq_model(object):

    def __init__(self, weights_path=None, iteration=0, load_all_vectors=True, ids_labels=[], original_labels=[]):

        #self.static_hyp(iteration)

        os.makedirs(weights_path, exist_ok=True)

        self.model = None
        self.num_classes = None
        self.weights_path = weights_path
        self.class_weights = None
        self.x_train = None
        self.x_val = None
        self.train_labels = None
        self.val_labels = None
        self.vocab = None
        self.load_all_vectors = load_all_vectors

        self.all_predictions = pd.DataFrame(original_labels, index=ids_labels, columns=["truth"])

    def static_hyp(self, iter):
        """Ensure reproducible results
        Ensure the reproducibility of the experiments by seeding the pseudo-random number generators and some other
        TensorFlow and Keras session configurations.
        Usage: Run this function before building your model. Moreover, run the *keras.backend.clear_session()* function
        after your experiment to restart with a fresh session.
        - Note that the most robust way to report results and compare models is to repeat your experiment many times (30+)
        and use summary statistics.
        References:
            https://keras.io/getting-started/faq/#how-can-i-obtain-reproducible-results-using-keras-during-development
            https://machinelearningmastery.com/reproducible-results-neural-networks-keras/
            https://stackoverflow.com/a/46886311/9933071
            
            seed1: 42 123 1234
            seed2: 41 122 1233
            seed3: 40 121 1230
            
        """

        # Set the random seed for NumPy. Keras gets its source of randomness from NumPy.
        np.random.seed(42)
        # Set the random seed for the TensorFlow backend.
        tf.random.set_seed(123+iter)
        # tf.set_random_seed(123)

        # Set the random seed for the core Python random number generator.
        # Not sure of the effectiveness of this, but it is recommended by Keras documentation.
        rn.seed(123)

    def build_model(self, data, layers=3, nodes=128, embedding_dim=300, dropout_rate=0.2,
                    vocabulary_size=10000, pretrained=True, embedding_trainable=False, bidirectional=True,
                    seq_len=64, emb_file=None, class_imbalance=True, algo="cnn", kernel_size=None,
                    vocab_dir=None, key=None, class_weights=None, initial_bias=None,
                    ):
        """

        :param data: a double tuple of arrays like numpy or lists, first tuple (train, labels), second (test,labels)
        :param layers: the number of layers
        :param nodes: the number of nodes, filters in the case of CNN
        :param embedding_dim: the dimension of the pre-trained embedding
        :param dropout_rate: dropout a real number [0,1]
        :param vocabulary_size: the desired size of the vocabulary
        :param pretrained: set to True if you are using pre-trained embeddings
        :param embedding_trainable: If the embedding layer has to be trained
        :param bidirectional: True if the LSTM is bidirectional
        :param seq_len: max length of the sentences
        :param emb_file: The file where you want to save the currents embeddings for futher experiments
        :param class_imbalance: True is the network must be trained to be sensitive to imbalance data
        :param algo: cnn Convolutional Network; rnn-fixed: LSTM network
        :param kernel_size: The kernel size fo CNN
        :param vocab_dir: the place where to save the embeddings vocabulary
        :param key: the unique key of the dataset
        :param class_weights: Auto if the weights must be calculated based on the number of samples.
        :param initial_bias:Auto if the bias must be calculated based on the number of samples.
        :return: info, Information about the current model.
                Number of words extracted,
                Max number of words for training
                Number of new embeddings found
                Max sequence length
                Class weights
                Initial bias
        """

        # Get the data.
        (train_texts, self.train_labels), (val_texts, self.val_labels) = data

        count_map = Counter(self.train_labels)
        self.num_classes = len(count_map)
        self.verify_labels(self.val_labels, self.num_classes)

        # Vectorized texts.
        vec = vectorize(features=vocabulary_size, doc_len=seq_len)
        self.x_train, self.x_val, word_index = vec.sequence_vectorize(train_texts, val_texts)

        num_features = min(len(word_index) + 1, vocabulary_size)

        we_name = "WE_" + key
        self.vocab = ProcessData.load_obj(vocab_dir, we_name)
        weights, n_emb = self.load_embeddigs_fast(emb_file, word_index, num_features, embedding_dim)

        ProcessData.save_obj(vocab_dir, we_name, self.vocab)

        if class_imbalance and self.num_classes == 2:
            if class_weights is "Auto":
                self.class_weights = self.weight_for_class_bin(count_map[0], count_map[1])
            else:
                self.class_weights = class_weights

            if initial_bias is "Auto":
                initial_bias = math.log(count_map[0] / count_map[1])

        if algo == "rnn-fixed":
            self.model = rnn_model_fixed(layers=layers,
                                         nodes=nodes,
                                         embedding_dim=embedding_dim,
                                         dropout_rate=dropout_rate,
                                         input_shape=self.x_train.shape[1:],
                                         num_classes=self.num_classes,
                                         num_features=num_features,
                                         use_pretrained_embedding=pretrained,
                                         is_embedding_trainable=embedding_trainable,
                                         embedding_matrix=weights,
                                         bidirectional=bidirectional,
                                         output_bias=initial_bias
                                         )

        if algo == "cnn":
            self.model = cnn_model(layers=layers,
                                   filters=nodes,
                                   filters_size=kernel_size,
                                   embedding_dim=embedding_dim,
                                   dropout_rate=dropout_rate,
                                   input_shape=self.x_train.shape[1:],
                                   num_classes=self.num_classes,
                                   num_features=num_features,
                                   use_pretrained_embedding=pretrained,
                                   is_embedding_trainable=embedding_trainable,
                                   embedding_matrix=weights,
                                   output_bias=initial_bias,
                                   text_len=seq_len
                                   )

        info = [len(word_index), self.x_train.shape[0], n_emb, seq_len, self.class_weights, initial_bias]
        return info

    def train_model(self, learning_rate=1e-4, epochs=20, batch_size=16, patience=3,
                    load_weights=False, weights_name=None, ad_data=([], []),
                    validation=True, monitor_measure="val_loss", method="Base", umbral=0.5,
                    score_method="avg", q=.98):

        loss = self.get_loss_type(self.num_classes)

        # print("Loss Type: ", loss)
        optimizer = tf.keras.optimizers.Adam(lr=learning_rate)
        callbacks = []
        model_temp = tf.keras.models.clone_model(self.model)

        model_temp.compile(optimizer=optimizer, loss=loss, metrics=['acc'])
        model_temp.summary()

        initial_weights = os.path.join(self.weights_path, weights_name)

        if validation:
            callbacks = [tf.keras.callbacks.EarlyStopping(monitor=monitor_measure, patience=patience),
                         tf.keras.callbacks.ModelCheckpoint(initial_weights, monitor=monitor_measure, verbose=1,
                                                            save_best_only=True, mode='auto')]

        if load_weights:
            model_temp.load_weights(weights_name)

        # Train and validate model.

        history = None

        if validation:
            history = model_temp.fit(
                self.x_train,
                self.train_labels,
                epochs=epochs,
                callbacks=callbacks,
                validation_data=(self.x_val, self.val_labels),
                verbose=2,  # Logs once per epoch.
                batch_size=batch_size, class_weight=self.class_weights)

            # Print results.
            history = history.history

        model_temp.load_weights(initial_weights)
        model_temp.compile(optimizer=optimizer, loss=loss, metrics=['acc'])

        y_pr_ = model_temp.predict(self.x_val, batch_size=batch_size)

        # Predictions as integers before average
        # y_pr_ = (y_pr_ > umbral).astype(int)

        (truths, lens) = ad_data
        sc = scores.Score(y_truth=self.val_labels, y_pred=y_pr_)

        if len(truths) > 0:
            if score_method == "avg":
                sc.join_pred(truths, lens, umbral)
            if score_method == "max":
                sc.max_pred(truths, lens, umbral, q)
        acc = sc.accuracy()
        f1 = sc.f1()
        f1_macro = sc.f1(mode="macro")

        # SAVE PREDICT
        if len(self.all_predictions.index) > 0:
            self.all_predictions[method + "_prob"] = sc.probabilities
            self.all_predictions[method + "_pred"] = sc.y_pred

        if validation:
            zeros = np.zeros(epochs - len(history["loss"]))

            h_loss = np.append(history["loss"], zeros)
            h_acc = np.append(history["acc"], zeros)
            h_val_loss = np.append(history["val_loss"], zeros)
            h_val_acc = np.append(history["val_acc"], zeros)

            new_history = np.append(h_loss, h_acc)
            new_history = np.append(new_history, h_val_loss)
            new_history = np.append(new_history, h_val_acc)

            score = [acc, f1[0], f1[1], f1[2], f1_macro[0], f1_macro[1], f1_macro[2], np.min(history["loss"]),
                     np.max(history["acc"]), np.min(history["val_loss"]),
                     np.max(history["val_acc"])]
            score = np.append(score, new_history)
        else:
            score = [acc, f1[0], f1[1], f1[2], f1_macro[0], f1_macro[1], f1_macro[2]]

        del model_temp
        gc.collect()

        return score

    def get_loss_type(self, num_classes):
        if num_classes == 2:
            loss = 'binary_crossentropy'
        else:
            loss = 'sparse_categorical_crossentropy'

        return loss

    def load_embeddigs_fast(self, file, word_index, features=20000, dim=300):

        if self.load_all_vectors:
            ft = fasttext.load_model(file)
        n_words_in = 0
        embedding_matrix = np.zeros((features, dim))
        for word, i in word_index.items():

            if i >= features:
                continue

            if word not in self.vocab:
                embedding_vector = ft.get_word_vector(word)
                self.vocab[word] = embedding_vector
                print("vocab")
                n_words_in += 1
            else:
                embedding_vector = self.vocab[word]

            embedding_matrix[i] = embedding_vector

        print("Number of new embeddings: ", n_words_in)

        return embedding_matrix, n_words_in

    def load_embeddigs_glove(self, glove_file, word_index, features=20000, dim=50):
        embeddings_index = {}
        coefs = np.zeros(300)
        f = open(glove_file, encoding="utf8")

        for line in f:
            values = line.split()
            word = values[0]
            try:
                coefs = np.asarray(values[1:], dtype='float32')
            except IndexError:
                pass
            embeddings_index[word] = coefs
        f.close()
        print('Total %s word vectors.' % len(embeddings_index))

        n_words_in = 0

        # Initialize embeddings
        # np.random.seed(42)
        # embedding_matrix = np.full((features, dim), np.random.rand(dim))
        embedding_matrix = np.zeros((features, dim))
        for word, i in word_index.items():

            if i >= features:
                continue

            embedding_vector = embeddings_index.get(word)
            if embedding_vector is not None:
                if len(embedding_matrix[i]) != len(embedding_vector):
                    print("could not broadcast input array from shape", str(len(embedding_matrix[i])),
                          "into shape", str(len(embedding_vector)), " Please make sure your"
                                                                    " EMBEDDING_DIM is equal to embedding_vector file "
                                                                    ",GloVe,")
                    exit(1)
                embedding_matrix[i] = embedding_vector
                n_words_in += 1
        print("Number of words with embeddings: ", n_words_in)

        return embedding_matrix, n_words_in

    def verify_labels(self, val_labels, num_classes):
        # Verify that validation labels are in the same range as training labels.
        unexpected_labels = [v for v in val_labels if v not in range(num_classes)]
        if len(unexpected_labels):
            raise ValueError('Unexpected label values found in the validation set:'
                             ' {unexpected_labels}. Please make sure that the '
                             'labels in the validation set are in the same range '
                             'as training labels.'.format(
                unexpected_labels=unexpected_labels))

    def weight_for_class_bin(self, n_neg, n_pos):
        """

        :param n_neg: number of negative instances
        :param n_pos: the number of positive instances
        :return:
        """
        weight_for_0 = (1 / n_neg) * (n_pos + n_neg) / 2.0
        weight_for_1 = (1 / n_pos) * (n_pos + n_neg) / 2.0

        return {0: weight_for_0, 1: weight_for_1}

    def save_predictions(self, path, file_name):
        complete_path = os.path.join(path, file_name + ".csv")
        self.all_predictions.to_csv(complete_path)
