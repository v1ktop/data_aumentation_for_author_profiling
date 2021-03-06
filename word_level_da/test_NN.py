# -*- coding: utf-8 -*-
"""
Created on Sat Jun 15 16:09:47 2019

@author: v1kto

This script test the model with: training - test, partitions


"""

import numpy as np
import tensorflow as tf
import warnings
from datetime import datetime
from word_level_da import utils
from word_level_da.preprocessing.load_data import Dataset
from word_level_da.classifier.train_sequence_model import seq_model
import os

#os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"
#os.environ["CUDA_VISIBLE_DEVICES"]="0,7"

warnings.filterwarnings("ignore")

OBJ_DIR = "D:/weights_rnn/depresion18v2/"
VOCAB_DIR = r"D:\v1ktop\Drive-INAOE\Code\data_aumentation_for_author_profiling\word_level_da\obj"
FAST300 = "D:/Models/fasttex/cc.en.300.bin"
tf.get_logger().setLevel('INFO')

if __name__ == "__main__":

    key = "depresion18_local"
    glove_file = FAST300
    batch_size = 1024
    epochs = 20
    layers = 1
    nodes = 300
    dim = 300
    label_pos = 1
    len_doc = 64
    kernel = 1
    max_features = 150000
    patience = 6
    drop = 0.2
    lr = 1e-3
    model = "cnn"
    AUGMENTED = True

    logger = utils.configure_root_logger(prefix_name=key + "_")
    utils.set_working_directory()

    logger.info("Testing %s dataset", key)
    logger.info("Model: %s", model)
    logger.info("Batch size: %d", batch_size)
    #    logger.info("Features: %d",max_features)
    logger.info("Epochs: %d", epochs)
    logger.info("Layers: %d", layers)
    logger.info("Nodes: %d", nodes)
    logger.info("drop: %f", drop)
    logger.info("lr: %f", lr)
    logger.info("Kernel size: %s", kernel)
    logger.info("Emb Dim: %d", dim)
    logger.info("Max Lenght: %d", len_doc)
    logger.info("Init Time: %s", datetime.now())

    # pairs=[(0,0)]

    data = Dataset(key=key, doc_len=len_doc, min_len=int(len_doc / 2), chunking=True, remove_end=True)
    training, test = data.get_train_test(return_ids=True)

    logger.info("Number of documents in training set: %s", len(training[0]))
    logger.info("Number of documents in test set: %s", len(test[0]))

    bi_gru = seq_model(weights_path=OBJ_DIR, iteration=1, load_all_vectors=False,
                       ids_labels=dict.fromkeys(test[2]).keys(), original_labels=test[3][0])

    methods = ["Rel_1"]
    n_docs = [i for i in range(1,11)]
    umbral = 0.4
    q = 75
    score_method = "avg"
    for augmentation_method in methods:
        for n in n_docs:

            prefix = augmentation_method + str(n)
            folder = augmentation_method + "/" + prefix
            truth_file = augmentation_method + "/" + prefix + ".txt"

            if AUGMENTED:
                docs, l_docs, ids, useless_data = data.get_dataset(folder_name=folder, truth_name=truth_file,
                                                                   partition="augmented")
                new_training = np.append(training[0], docs)
                new_labels = np.append(training[1], l_docs)
            else:
                new_training = training[0]
                new_labels = training[1]

            info = bi_gru.build_model(((new_training, new_labels), (test[0], test[1])), layers=layers, nodes=nodes,
                                      embedding_dim=dim,vocabulary_size=max_features, kernel_size=[3,4,5], dropout_rate=drop,
                                      pretrained=True, embedding_trainable=False, bidirectional=True,
                                      seq_len=len_doc, emb_file=glove_file, class_imbalance=True, algo=model,
                                      vocab_dir=VOCAB_DIR, key=key.split("_")[0], class_weights="Auto",
                                      initial_bias="Auto")

            #logger.info("Vocabulary size: %d", info[0])
            info[2] = umbral

            for iteration in range(3):
                score = bi_gru.train_model(lr, epochs, batch_size, patience, load_weights=False,
                                               weights_name=key.split("_")[0] + prefix + model + str(iteration) + ".h5",
                                               ad_data=(test[3]),
                                               validation=True, monitor_measure="val_loss",
                                               method=augmentation_method + str(iteration),
                                               umbral=umbral, score_method=score_method, q=q)

                info_s = [augmentation_method, n, iteration]
                info_s += info
                info_s += list(score)
                logger.info(info_s)

    bi_gru.save_predictions(VOCAB_DIR, "predictions_" + key + model)
    logger.info("Finish Time: %s", datetime.now())
