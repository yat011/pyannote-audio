#!/usr/bin/env python
# encoding: utf-8

# The MIT License (MIT)

# Copyright (c) 2014-2016 CNRS

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# AUTHORS
# Hervé BREDIN - http://herve.niderb.fr

import matplotlib
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    matplotlib.use('Agg')
import matplotlib.pyplot as plt

from keras.callbacks import Callback
from sklearn.metrics import precision_recall_curve
import numpy as np
import scipy.stats


class EmbeddingCheckpoint(Callback):

    def __init__(self, sequence_embedding,
                       checkpoint='weights.{epoch:03d}-{loss:.2f}.hdf5'):
        super(EmbeddingCheckpoint, self).__init__()
        self.sequence_embedding = sequence_embedding
        self.checkpoint = checkpoint

    def on_epoch_end(self, epoch, logs={}):
        weights = self.checkpoint.format(epoch=epoch, **logs)
        try:
            self.sequence_embedding.to_disk(
                weights=weights, overwrite=True, model=self.model)
        except Exception as e:
            # chat échaudé craint l'eau froide
            pass

class ValidationCheckpoint(Callback):

    def __init__(self, sequence_embedding, generator, protocol, checkpoint='/tmp/checkpoint'):
        super(ValidationCheckpoint, self).__init__()
        self.sequence_embedding = sequence_embedding
        self.generator = generator
        self.protocol = protocol
        self.checkpoint = checkpoint
        self.accuracy = {'train': [], 'dev': [], 'test': []}
        self.fscore = {'train': [], 'dev': [], 'test': []}
        self.loss = []

    def validation(self, file_generator):

        embedding = self.sequence_embedding.get_embedding(self.model)

        Y, Distance = [], []

        for batch in self.generator(file_generator, infinite=False):
            (query, returned), y = batch
            Xq = embedding.predict_on_batch(query)
            Xr = embedding.predict_on_batch(returned)
            distance = np.sum((Xq - Xr) ** 2, axis=-1)
            Distance.append(distance)
            Y.append(y)
        y = np.hstack(Y)
        distance = np.hstack(Distance)

        precision, recall, thresholds = precision_recall_curve(
            y, -distance, pos_label=True)
        thresholds = -thresholds

        fscore = np.hstack([scipy.stats.hmean(np.vstack([precision, recall])[:,:-1], axis=0), [0]])
        accuracy = [np.mean(y == (distance < threshold))
                    for threshold in thresholds]

        return y, distance, thresholds, precision, recall, fscore, accuracy

    def on_epoch_end(self, epoch, logs={}):

        self.loss.append(logs['loss'])

        plt.figure(figsize=(12, 12))

        bins = np.arange(0, 2, 0.05)

        train_then_dev = [('train', self.protocol.train_iter()), ('dev', self.protocol.dev_iter())]
        for i, (dataset, file_generator) in enumerate(train_then_dev):

            y, distance, thresholds, precision, recall, fscore, accuracy = self.validation(file_generator)

            # find threshold maximizing accuracy
            A = np.argmax(accuracy)
            accuracy_threshold = thresholds[A]
            self.accuracy[dataset].append(accuracy[A])

            # find threshold maximizing f-score
            F = np.argmax(fscore)
            fscore_threshold = thresholds[F]
            self.fscore[dataset].append(fscore[F])

            # plot inter- vs. intra-class distance distributions
            plt.subplot(3, 3, 3 * i + 1)
            plt.hist(distance[y], bins=bins, color='g', alpha=0.5, normed=True)
            plt.hist(distance[~y], bins=bins, color='r', alpha=0.5, normed=True)
            plt.ylim(0, 3)
            plt.title(dataset)

            # plot precision / recall curve
            # show best operating point
            plt.subplot(3, 3, 3 * i + 2)
            plt.plot(recall, precision, 'b')
            plt.plot([recall[F]], [precision[F]], 'bo')
            plt.xlabel('Recall')
            plt.ylabel('Precision')
            plt.title('F-Score = {fscore:.3f}'.format(
                fscore=self.fscore[dataset][-1]))
            plt.xlim(0, 1)
            plt.ylim(0, 1)

            # plot fscore and accuracy curves
            # show best operating points
            plt.subplot(3, 3, 3 * i + 3)
            plt.plot(thresholds, accuracy, 'g')
            plt.xlabel('Threshold')
            plt.xlim(np.min(bins), np.max(bins))
            plt.ylim(0, 1)
            plt.plot([thresholds[A]], [accuracy[A]], 'go')
            plt.title('Accuracy = {accuracy:.3f}'.format(
                accuracy=self.accuracy[dataset][-1]))

        # test set
        file_generator = self.protocol.test_iter()
        y, distance, thresholds, precision, recall, fscore, accuracy = self.validation(file_generator)

        # find threshold most similar to the ones selected on dev
        [a, f] = np.searchsorted(-thresholds, [-accuracy_threshold, -fscore_threshold])
        # evaluate accuracy with dev-optimized threshold
        self.accuracy['test'].append(accuracy[a])
        # evaluate fscore with dev-optimized threshold
        self.fscore['test'].append(fscore[f])

        # plot inter- vs. intra-class distance distributions
        plt.subplot(3, 3, 7)
        plt.hist(distance[y], bins=bins, color='g', alpha=0.5, normed=True)
        plt.hist(distance[~y], bins=bins, color='r', alpha=0.5, normed=True)
        plt.ylim(0, 3)
        plt.title('test')

        # plot precision / recall
        # show dev-optimized operating point
        plt.subplot(3, 3, 8)
        plt.plot(recall, precision, 'b')
        plt.plot([recall[f]], [precision[f]], 'bo')
        plt.xlabel('Recall')
        plt.ylabel('Precision')
        plt.title('F-Score = {fscore:.3f}'.format(
            fscore=self.fscore['test'][-1]))
        plt.xlim(0, 1)
        plt.ylim(0, 1)

        # plot fscore and accuracy curves
        # show dev-optimized operating points
        plt.subplot(3, 3, 9)
        plt.plot(thresholds, accuracy, 'g', label='accuracy')
        plt.xlabel('Threshold')
        plt.xlim(np.min(bins), np.max(bins))
        plt.ylim(0, 1)
        plt.plot([thresholds[a]], [accuracy[a]], 'go')
        plt.title('Accuracy = {accuracy:.3f}'.format(
            accuracy=self.accuracy['test'][-1]))

        plt.tight_layout()

        try:
            plt.savefig(self.checkpoint + '/{epoch:03d}.png'.format(epoch=epoch), dpi=50)
            plt.savefig(self.checkpoint + '/latest.png', dpi=150)
            plt.savefig(self.checkpoint + '/latest.eps')
        except Exception as e:
            # chat échaudé craint l'eau froide
            pass

        plt.close()

        plt.figure(figsize=(12, 4))

        plt.subplot(1, 3, 1)
        plt.plot(self.loss, 'b')
        plt.xlabel('Epoch')
        plt.title('Loss')

        plt.subplot(1, 3, 2)
        plt.plot(self.accuracy['train'], 'g', label='train')
        plt.plot(self.accuracy['dev'], 'b', label='dev')
        plt.plot(self.accuracy['test'], 'r', label='test')
        plt.xlabel('Epoch')
        plt.ylim(0, 1)
        plt.title('Accuracy')
        plt.legend(loc='lower right')

        plt.subplot(1, 3, 3)
        plt.plot(self.fscore['train'], 'g', label='train')
        plt.plot(self.fscore['dev'], 'b', label='dev')
        plt.plot(self.fscore['test'], 'r', label='test')
        plt.xlabel('Epoch')
        plt.ylim(0, 1)
        plt.title('F-Score')
        plt.legend(loc='lower right')

        plt.tight_layout()

        try:
            plt.savefig(self.checkpoint + '/status.png', dpi=150)
            plt.savefig(self.checkpoint + '/status.eps')
        except Exception as e:
            # chat échaudé craint l'eau froide
            pass

        plt.close()
