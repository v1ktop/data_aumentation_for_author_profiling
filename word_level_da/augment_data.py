"""
Execute this script to augment your data locally

"""
import os
import numpy as np
from collections import defaultdict
from word_level_da import utils
from word_level_da.preprocessing.load_data import Dataset
from word_level_da.preprocessing.process_data import ProcessData
from word_level_da.augmentation.syn_rep import SynRep
from word_level_da.augmentation.select_candidates import select_docs

GLOVE_DIR = "D:/Models/glove/glove.42B/glove.42B.300d.txt"


def augment_by_docs_one_class(lan, output, glove_file, augmentation_method="Over",
                              replace="glove",
                              label_to_aug=None, labels=None, obj_label=1,
                              n_docs=None, dataset_key="erisk18_dev",
                              load_emb=True, load_obj=False, preproces_vocab=False,
                              vocab_dir="D:/v1ktop/Drive/REPOS/augmentation_ap/obj/",
                              analogy_file="file",
                              filter=True,
                              p_confidence=0.001, min_ocurrence=20, doc_len=64, p_aug=0.1,
                              save_words=False, curren_n=1, label_file="train_golden_truth_joined.txt",
                              folder="prep_chunks_joined"
                              ):
    if n_docs is None:
        n_docs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    logger.info("Loading positive documents")

    data = Dataset(key=dataset_key, encode=False, remove_end=False, doc_len=doc_len,
                   min_len=int(doc_len / 2), chunking=True)

    # Get dataset in chunks
    docs_train, truths_train, author_ids_train, (truths, lens) = data.get_dataset(partition="training",
                                                                                  folder_name=folder,
                                                                                  truth_name=label_file,
                                                                                  )

    # read augmented data

    new_training = docs_train
    new_labels = truths_train

    for i in range(1, curren_n):
        prefix = augmentation_method + str(curren_n - 1)
        folder = augmentation_method + "/" + prefix
        truth_file = augmentation_method + "/" + prefix + ".txt"
        docs, l_docs, ids, useless_data = data.get_dataset(folder_name=folder, truth_name=truth_file,
                                                           partition="augmented")

        new_training = np.append(docs_train, docs)
        new_labels = np.append(truths_train, l_docs)

    selection = select_docs(docs_train, truths_train, author_ids_train, top_words_path=obj_dir,
                            top_words_file="top_words_" + dataset_key)

    new_words = selection.get_top_words(confidence=p_confidence, docs_training=new_training,
                                        labels_training=new_labels, save_words=save_words)

    logger.info("New words %s", new_words)

    if filter:
        cand_ids, cand_labels, cand_docs = selection.select_by_ocurrence(max_ocurrence=min_ocurrence,
                                                                         obj_label=obj_label)
    else:
        cand_ids, cand_labels, cand_docs = selection.select_by_class(obj_label=obj_label)

    logger.info("Number of selected docs %d", len(cand_ids))

    logger.info("Loading glove")

    syn_augmented = SynRep(glove_file=glove_file, lang=lan, replace=replace,
                           load_embedding=load_emb, load_obj=load_obj, obj_dir=vocab_dir,
                           voc_name=dataset_key, pos_file="pos_" + dataset_key, analogy_file=analogy_file)

    if augmentation_method == "Xi":
        syn_augmented.top_words = selection.top_words

    logger.info("Top features: %s", selection.top_words)
    logger.info("Number of Top features: %s", len(selection.top_words))

    logger.info("Augmenting docs")

    if preproces_vocab:
        logger.info("Loading vocabulary")

        syn_augmented.build_all_vocab(cand_docs, label_to_aug)

        logger.info("Loading vocabulary successful")
        logger.info("Vocabulary without stop words %d", syn_augmented.total_words)
        logger.info("Number of words with vectors %d", syn_augmented.words_with_vec)

    uniques_ids = defaultdict(list)

    for c_id, c_label, c_doc in zip(cand_ids, cand_labels, cand_docs):
        uniques_ids[c_id].append(c_doc)

    ids_to_aug = []
    truths_to_aug = [obj_label] * len(uniques_ids)

    for num_aug in n_docs:
        syn_augmented.reps_by_doc = np.zeros(len(cand_docs))
        syn_augmented.words_by_doc = np.zeros(len(cand_docs))
        augmented_docs = []
        n_augs = []
        c = 0
        for i, key in enumerate(uniques_ids.keys()):

            docs = uniques_ids[key]
            ids_to_aug.append(key)
            print(ids_to_aug[i])
            # lines=doc.split('end_')

            new_docs = []
            n_augs.append(num_aug)

            current_label = labels[truths_to_aug[i]]
            # print(n_docs)
            for doc in docs:

                if augmentation_method == "Rel_1" or augmentation_method == "Rel_0":
                    new_chunks, nrep = syn_augmented.augment_post(post=doc,
                                                                  num_aug=num_aug, method=augmentation_method,
                                                                  doc_index=i,
                                                                  from_class=current_label,
                                                                  to_class=label_to_aug[current_label], p_select=p_aug,
                                                                  )

                else:
                    new_chunks, nrep = syn_augmented.augment_post(post=doc,
                                                                  num_aug=num_aug, method=augmentation_method,
                                                                  doc_index=i,
                                                                  from_class=None,
                                                                  to_class=None, p_select=p_aug)

                new_docs.append(new_chunks)

            for l in range(num_aug):
                single = []
                for m in range(len(new_docs)):
                    # print(m)
                    # print(l)
                    single.append(new_docs[m][l])

                augmented_docs.append(single)

            c += num_aug
            if c % 10 == 0:
                print('Augmented:' + str(c))

        prefix = augmentation_method + str(num_aug)

        complete_out_dir = os.path.join(output, augmentation_method)

        if preproces_vocab:
            syn_augmented.save_files()

        labels_to_save = ["1"] * len(uniques_ids)

        new_ids = ProcessData.write_augmented_labels(ids_to_aug, labels_to_save, n_augs,
                                                     complete_out_dir, prefix)

        ProcessData.plain_docs_to_txt(new_ids, augmented_docs, complete_out_dir, prefix)

        stats_words = syn_augmented.get_stats_words()
        stats_rep = syn_augmented.get_stats_words_rep()
        data = [dataset_key, augmentation_method, num_aug, stats_words["mean"], stats_rep["mean"]]
        logger.info(data)


if __name__ == "__main__":
    """
    Over: Oversamplig
    Thesaurus: 
    Xi
    Context_1
    Rel_1
    Rel_0
    
    """
    obj_dir = r"D:\v1ktop\Drive-INAOE\Code\data_aumentation_for_author_profiling\word_level_da\obj"
    method = "Xi"
    dataset_key ="depresion19_local"
    # dataset_key="anorexia18_dev"
    lang = 'en'

    labels_dic = {"depressed": ["anxious", "frustrated", "unhappy", "despondent", "discouraged"]}
    labels = {0: "happiness", 1: "depressed"}
    # labels={0:"healthy", 1:"anorexic"}
    # labels_dic={"healthy":["bulimic", "underweight", "obese", "malnourished", "unhealthy"]}

    #output_dir = "D:/corpus/anorexia/2018/train/augmented-xi-filter/"
    #output_dir = "D:/corpus/DepresionEriskCollections/2017/train/augmented/"
    output_dir = "D:/corpus/DepresionEriskCollections/2019/train/augmented-xi/"
    logger = utils.configure_root_logger(prefix_name=method + "_" + dataset_key)
    utils.set_working_directory()

    logger.info("Running data augmentation for the dataset: %s", dataset_key)
    logger.info("Method: %s", method)
    logger.info("Labels: %s", labels_dic[labels[1]])

    p_select = 0.2

    """
        replace:
                wordnet: for thesaurus method
                glove: for Xi
                analogy: for Context_1, Context_0
                
                save_words=True at first run (1,2)
                False otherwise
                n_docs= Number of augmented documents at this run
                curren_n= current augmentation for incremental training must be greater than one
                
    """
    augment_by_docs_one_class(lan=lang, output=output_dir, glove_file=GLOVE_DIR, augmentation_method=method,
                              replace="glove", label_to_aug=labels_dic, labels=labels, obj_label=1,
                              n_docs=[i for i in range(1, 11)], dataset_key=dataset_key, load_emb=False, load_obj=True,
                              preproces_vocab=False, vocab_dir=obj_dir, analogy_file="r0_" + dataset_key, filter=False,
                              min_ocurrence=20, p_aug=p_select, save_words=True, curren_n=1,
                              label_file= "golden_truth.txt",
                              folder="prep_chunks/")
