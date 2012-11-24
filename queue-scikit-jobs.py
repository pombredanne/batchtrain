#!/usr/bin/python
"""
Brute force learn the problem, using scikit.
WARNING: We convert ALL features to DENSE!
"""

import sys
import string
import simplejson
import re

JOBS_PER_FILE = 250

#CACHESIZE = 4000    # For local
CACHESIZE = 1200 # For ec2 small
#CACHESIZE = 400 # For ec2 computation nodes

#KFOLD = True
KFOLD = False

import os
from collections import OrderedDict

try:
#    from common.timeout import timeout
    from common.stats import stats
except:
    from stats import stats
#    stats = lambda: None

import itertools
import random

#random.seed(0)

import glob

# Code from http://rosettacode.org/wiki/Power_set#Python
def list_powerset2(lst):
    return reduce(lambda result, x: result + [subset + [x] for subset in result],
                  lst, [[]])
def powerset(s):
    return frozenset(map(frozenset, list_powerset2(list(s))))

def svmhyperparameters():
    HYPERPARAMS = OrderedDict({
        # 0.01-0.1, 10 aren't good. 1 is okay. 32 and 100 are good.
        # 320 and 100 is not good for training with DBN. 23 is okay.
        #"C": [0.01, 0.1, 1, 10, 100],
        "C": [3.2, 10, 32, 100, 320, 1000],
        #"C": [1, 3.2, 10],
        # 1 isn't good. 0.01 is okay.
        # 0.001 and isn't good for training with DBN.
        "epsilon": [0.001, 0.01, 0.1, 1.0],
        # sigmoid, linear isn't good. poly is okay.
        "kernel": ["rbf"],
        # 1 and 3 is okay.
        #"degree": [2,4,5],
        "degree": [1,2,3,4,5],
        #"degree": [2,5],
        # 0.0001, 0.001, 0.01, 0.1, 1 isn't good
        "gamma": [0.],
        "cache_size": [CACHESIZE],
#        # False is not good for task 7
        "shrinking": [False, True],
    })
    hyperparams = list(itertools.product(*HYPERPARAMS.values()))
    # We don't remove redundant hyperparams because we want to randomize over gamma and degree.
    # Reason being, we do random hyperparameter search, and don't have
    # logic to figure out which are redundant when picking the best ones.
    # i.e. if we picked the hyperparams deterministically when they
    # aren't used, there would be a bias towards thinking those are OVERALL
    # the best.
#    nonredundant_hyperparams = []
#    for h in hyperparams:
#        dicth = dict(zip(HYPERPARAMS.keys(), h))
#        if dicth["kernel"] != "linear":
#            nonredundant_hyperparams.append(h)
#        # degree and gamma are not used for linear kernel, so only use one hyperparam for these
#        elif dicth["degree"] == HYPERPARAMS["degree"][1] and dicth["gamma"] == HYPERPARAMS["gamma"][1]:
#            nonredundant_hyperparams.append(h)
#    hyperparams = nonredundant_hyperparams
    random.shuffle(hyperparams)
    for h in hyperparams:
        yield dict(zip(HYPERPARAMS.keys(), h))

def gbrhyperparameters():
    HYPERPARAMS = OrderedDict({
        # 'lad' isn't good
        'loss': ['ls'],
        'learn_rate': [0.032, 0.01],
        # 32 isn't good. 100 is okay.
        'n_estimators': [320, 1000],
        # 1-2 aren't good. 3 is okay. 10 is not good.
        'max_depth': [4,6,8],
        'min_samples_split': [1,3],
        # 10 isn't good
        'min_samples_leaf': [1, 3],
        # 0.1 isn't good, 0.5 is okay.
        'subsample': [0.75, 1],
    })
    hyperparams = list(itertools.product(*HYPERPARAMS.values()))
    random.shuffle(hyperparams)
    for h in hyperparams:
        yield dict(zip(HYPERPARAMS.keys(), h))

def rfrhyperparameters():
    HYPERPARAMS = OrderedDict({
        # 10 isn't good
        'n_estimators': [32, 50, 100, 200],
        # 1, 3 aren't good. 10 is okay.
        'max_depth': [None],
        # 1 is okay.
        'min_samples_split': [3,10],
        'min_samples_leaf': [1,3,10],
        # 0.32 is okay.
        'min_density': [0.01, 0.032, 0.1],
        # False isn't good
        'bootstrap': [True],
        'oob_score': [True, False],
#        'verbose': [True],
    })
    hyperparams = list(itertools.product(*HYPERPARAMS.values()))
    random.shuffle(hyperparams)
    for h in hyperparams:
        yield dict(zip(HYPERPARAMS.keys(), h))

if __name__ == "__main__":
    modelconfigs = []
#    for regressor, hfunc in [(GradientBoostingRegressor, gbrhyperparameters), (RandomForestRegressor, rfrhyperparameters), (svm.SVR, svmhyperparameters)]:
#    for regressor, hfunc in [("GradientBoostingRegressor", gbrhyperparameters), ("RandomForestRegressor", rfrhyperparameters)]:
    for regressor, hfunc in [("SVR", svmhyperparameters)]:
        oldlen = len(modelconfigs)
        for h in hfunc():
            modelconfigs.append((regressor, h))
        print >> sys.stderr, "%d model configurations for %s" % (len(modelconfigs)-oldlen, regressor)
    random.shuffle(modelconfigs)
    print >> sys.stderr, "%d model configurations" % len(modelconfigs)

    numfeatures = []
    for num in [7,4,14,9,3,5,15,11,13,2,12,8,10,6,1]:
#    for num in [3]:
        deepfeatures = set()
        # Find all models
        for d in glob.glob("model/*/%d.*" % num):
            # pretrain_lr=0.01 isn't as good as 0.1 or 0.032, i.e. IGNORE pretrain_lr=0.01
            if d.find("pretrain_lr=0.01") != -1: continue
            modelfeatures = []
            # Find all layers in the model
            for d2 in glob.glob("%s/layer*" % d):
                # Find last saved model at this layer
                layerfeature = None
                epoch_layerfeature = []
                for layerfeature in reversed(sorted(glob.glob("%s/representation*.pkl.gz" % d2))):
                    epochre = re.compile("representation.epoch-(\d+)\.")
                    epoch_layerfeature.append((int(epochre.search(layerfeature).group(1)), layerfeature))
#                if not layerfeature: continue
                if not len(epoch_layerfeature): continue
                epoch_layerfeature.sort()
                epoch_layerfeature.reverse()
                layerfeature = epoch_layerfeature[0][1]
                modelfeatures.append(layerfeature)
#            print modelfeatures
            for f in powerset(modelfeatures):
                deepfeatures.add(tuple(sorted(f)))

        # Skip instances with no deep features (optional)
        if len(deepfeatures) == 0: continue

        # Find all possible basic features
        # datagz/sparse.train%d-all.norm.train.pkl.gz is not good for task 7.
        basicfeatures = [tuple(sorted(f)) for f in powerset(["datagz/sparse.train%d-all.unnorm.train.pkl.gz" % num, "datagz/sparse.train%d-all.norm.train.pkl.gz" % num])]
        #basicfeatures = [tuple(sorted(f)) for f in powerset(["datagz/sparse.train%d-all.unnorm.train.pkl.gz" % num])]

        # Combine deep features and basic features
        features = []
        for f1 in basicfeatures:
            for f2 in deepfeatures:
                if not len(f1) and not len(f2): continue
                features.append(f1 + f2)
        fset = [(num, f) for f in features]
        random.shuffle(fset)
        numfeatures += fset

    print >> sys.stderr, "%d feature set combinations" % len(numfeatures)

    mn = list(itertools.product(modelconfigs, numfeatures))
    random.shuffle(mn)
    print >> sys.stderr, "%d total jobs" % len(mn)
    print >> sys.stderr, stats()

    files = 0
    cmds = []
    for i, (modelconfig, numfeatures) in enumerate(mn):
        regressor, h = modelconfig
        num, features = numfeatures
        cmd = "./job-brutescikit.py --kfold --regressor %s --hyperparameters %s --num %d %s" % (regressor, repr(simplejson.dumps(h)), num, string.join(features))
        cmds.append(cmd)
        
        files += 1
        if files % JOBS_PER_FILE == 0:
            jobcmd = "job%06d.sh" % (files/JOBS_PER_FILE)
            jobfile = open(jobcmd, "wt")
            jobfile.write("#!/bin/sh\n")
            for cmd in cmds:
                jobfile.write(cmd + "\n")
            cmds = []
            os.system("chmod +x %s" % jobcmd)
            print "qsub -V -b y -cwd ./%s" % jobcmd
            sys.stdout.flush()
            
#        if i > 1000: break
#        try:
#            job(regressor, h, num, features)
#        except Exception, e:
#            print >> sys.stderr, type(e), e