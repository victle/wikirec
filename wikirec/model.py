"""
model
-----

Functions for modeling text corpuses and producing recommendations

Contents:
    gen_sim_matrix,
    recommend
"""

from collections import Counter
import math

import numpy as np

from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from sklearn.feature_extraction.text import TfidfVectorizer

import gensim
from gensim import corpora, models, similarities
from gensim.models.ldamulticore import LdaMulticore
from gensim.models import CoherenceModel
from gensim.models.doc2vec import Doc2Vec, TaggedDocument

from sentence_transformers import SentenceTransformer

from wikirec import utils


def gen_sim_matrix(
    method="lda",
    metric="cosine",
    corpus=None,
    bert_st_model="xlm-r-bert-base-nli-stsb-mean-tokens",
    **kwargs,
):
    """
    Derives similarities between the entries in the text corpus

    Parameters
    ----------
        method : str (default=lda)
            The modelling method

            Options:
                BERT: Bidirectional Encoder Representations from Transformers

                    - Words embeddings are derived via Google Neural Networks

                    - Embeddings are then used to derive similarities

                Doc2vec : Document to Vector

                    - An entire document is converted to a vector

                    - Based on word2vec, but maintains the document context

                LDA: Latent Dirichlet Allocation

                    - Text data is classified into a given number of categories

                    - These categories are then used to classify individual entries given the percent they fall into categories

                TFIDF: Term Frequency Inverse Document Frequency

                    - Word importance increases proportionally to the number of times a word appears in the document while being offset by the number of documents in the corpus that contain the word

                    - These importances are then vectorized and used to relate documents

        metric : str (default=cosine)
            The metric to be used when comparing vectorized corpus entries

            Options include: cosine and euclidean

        corpus : list or list of lists (default=None)
            The text corpus over which analysis should be done

        bert_st_model : str (deafault=xlm-r-bert-base-nli-stsb-mean-tokens)
            The BERT model to use

        **kwargs : keyword arguments
            Arguments correspoding to sentence_transformers.SentenceTransformer.encode, gensim.models.doc2vec.Doc2Vec, gensim.models.ldamulticore.LdaMulticore, or sklearn.feature_extraction.text.TfidfVectorizer

    Returns
    -------
        sim_matrix : gensim.interfaces.TransformedCorpus or numpy.ndarray
            The similarity sim_matrix for the corpus from the given model
    """
    method = method.lower()

    valid_methods = ["bert", "doc2vec", "lda", "tfidf"]

    if method not in valid_methods:
        raise ValueError(
            "The value for the 'method' argument is invalid. Please choose one of ".join(
                valid_methods
            )
        )

    if method == "bert":
        bert_model = SentenceTransformer(bert_st_model)

        document_embeddings = bert_model.encode(corpus, **kwargs)

        if metric == "cosine":
            sim_matrix = cosine_similarity(document_embeddings)

        elif metric == "euclidean":
            sim_matrix = euclidean_distances(document_embeddings)

        return sim_matrix

    elif method == "doc2vec":
        tagged_data = [
            TaggedDocument(words=tc_i, tags=[i]) for i, tc_i in enumerate(corpus)
        ]

        if "vector_size" in kwargs:
            vector_size = kwargs.get("vector_size")
        else:
            vector_size = 100

        model_d2v = Doc2Vec(vector_size=vector_size, **kwargs)
        model_d2v.build_vocab(tagged_data)

        for _ in range(vector_size):
            model_d2v.train(
                documents=tagged_data,
                total_examples=model_d2v.corpus_count,
                epochs=model_d2v.epochs,
            )

        document_embeddings = np.zeros((len(tagged_data), vector_size))
        for i in range(len(document_embeddings)):
            document_embeddings[i] = model_d2v.docvecs[i]

        if metric == "cosine":
            sim_matrix = cosine_similarity(document_embeddings)

        elif metric == "euclidean":
            sim_matrix = euclidean_distances(document_embeddings)

        return sim_matrix

    elif method == "lda":
        dictionary = corpora.Dictionary(corpus)
        bow_corpus = [dictionary.doc2bow(text) for text in corpus]

        model_lda = LdaMulticore(corpus=bow_corpus, id2word=dictionary, **kwargs)

        if metric == "cosine":
            sim_index = similarities.MatrixSimilarity(model_lda[bow_corpus])

        elif metric == "euclidean":
            print(
                "Euclidean distance is not implemented for LDA modeling at this time. Please use 'cosine' for the metric argument."
            )
            return

        vectors = model_lda[bow_corpus]
        sim_matrix = sim_index[vectors]

        return sim_matrix

    elif method == "tfidf":
        tfidfvectoriser = TfidfVectorizer(**kwargs)
        tfidfvectoriser.fit(corpus)
        tfidf_vectors = tfidfvectoriser.transform(corpus)

        if metric == "cosine":
            sim_matrix = np.dot(  # pylint: disable=no-member
                tfidf_vectors, tfidf_vectors.T
            ).toarray()

        elif metric == "euclidean":
            sim_matrix = euclidean_distances(tfidf_vectors)

        return sim_matrix


# Allow for !arguments


def recommend(
    inputs=None, titles=None, sim_matrix=None, n=10,
):
    """
    Recommends similar items given an input or list of inputs of interest

    Parameters
    ----------
        inputs : str or list (default=None)
            The name of an item or items of interest

        titles : lists (default=None)
            The titles of the articles

        sim_matrix : gensim.interfaces.TransformedCorpus or np.ndarray (default=None)
            The similarity sim_matrix for the corpus from the given model

        n : int (default=10)
            The number of items to recommend

    Returns
    -------
        recommendations : list of lists
            Those items that are most similar to the inputs and their similarity scores
    """
    if type(inputs) == str:
        inputs = [inputs]

    first_input = True
    for inpt in inputs:
        checked = 0
        num_missing = 0
        for i in range(len(titles)):
            if titles[i] == inpt:
                if first_input == True:
                    sims = sim_matrix[i]

                    first_input = False

                else:
                    sims = [
                        np.mean([sims[j], sim_matrix[i][j]]) for j in range(len(sims))
                    ]

            else:
                checked += 1
                if checked == len(titles):
                    num_missing += 1
                    print(f"{inpt} not available")
                    utils._check_str_args(arguments=inpt, valid_args=titles)

                    if num_missing == len(inputs):
                        ValueError(
                            "None of the provided inputs were found in the index. Please check them and reference Wikipedia for valid inputs via article names."
                        )

    titles_and_scores = [[titles[i], sims[i]] for i in range(len(titles))]

    if sim_matrix.all() <= 1:
        # Cosine similarities have been used (higher is better)
        recommendations = sorted(titles_and_scores, key=lambda x: x[1], reverse=True)
    else:
        # Euclidean distances have been used (lower is better)
        recommendations = sorted(titles_and_scores, key=lambda x: x[1], reverse=False)

    recommendations = [r for r in recommendations if r[0] not in inputs][:n]

    return recommendations
