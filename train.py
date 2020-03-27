from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
from datetime import date
import logging
import json
import random
import time
import math
from collections import OrderedDict
import torch
import torch.nn as nn
import torch.optim
import tqdm
import pickle
import itertools
import speech
import speech.loader as loader
import speech.models as models

# TODO, (awni) why does putting this above crash..
import tensorboard_logger as tb


def run_epoch(model, optimizer, train_ldr, logger, it, avg_loss):
    """
    Performs a forwards and backward pass through the model
    """
    use_log = (logger is not None)
    model_t = 0.0; data_t = 0.0
    end_t = time.time()
    tq = tqdm.tqdm(train_ldr)
    for batch in tq:
        if use_log: logger.info(f"====== Inside run_epoch =======")

        temp_batch = list(batch)    # this was added as the batch generator was being exhausted when it was called
        start_t = time.time()
        optimizer.zero_grad()
        if use_log: logger.info(f" Optimizer zero_grad")

        loss = model.loss(temp_batch)
        if use_log: logger.info(f" Loss calculated")

        #print(f"loss value 1: {loss.data[0]}")
        loss.backward()
        if use_log: logger.info(f" Backward run ")


        grad_norm = nn.utils.clip_grad_norm_(model.parameters(), 200)
        if use_log: logger.info(f" Grad_norm clipped ")

        loss = loss.item()
        if use_log: logger.info(f" loss reassigned ")

        #loss = loss.data[0]

        optimizer.step()
        if use_log: logger.info(f" Grad_norm clipped ")

        prev_end_t = end_t
        end_t = time.time()
        model_t += end_t - start_t
        data_t += start_t - prev_end_t
        if use_log: logger.info(f" time calculated ")


        exp_w = 0.99
        avg_loss = exp_w * avg_loss + (1 - exp_w) * loss
        if use_log: logger.info(f"Avg loss: {loss}")
        tb.log_value('train_loss', loss, it)
        tq.set_postfix(iter=it, loss=loss,
                avg_loss=avg_loss, grad_norm=grad_norm,
                model_time=model_t, data_time=data_t)
        if use_log: logger.info(f"loss is nan: {math.isnan(loss)}")
        if use_log: logger.info(f"iter={it}, loss={round(loss,3)}, grad_norm={round(grad_norm,3)}")
        inputs, labels, input_lens, label_lens = model.collate(*temp_batch)

        if check_nan(model):
            if use_log: logger.error(f"labels: {[labels]}, label_lens: {label_lens} state_dict: {model.state_dict()}")

        it += 1

    return it, avg_loss

def eval_dev(model, ldr, preproc,  logger):
    losses = []; all_preds = []; all_labels = []
        
    model.set_eval()
    preproc.set_eval()
    use_log = (logger is not None)
    if use_log: logger.info(f" set_eval ")


    with torch.no_grad():
        for batch in tqdm.tqdm(ldr):
            temp_batch = list(batch)
            if use_log: logger.info(f"batch converted")
            preds = model.infer(temp_batch)
            if use_log: logger.info(f"infer call")
            loss = model.loss(temp_batch)
            if use_log: logger.info(f"loss calculated as: {loss.item():0.3f}")
            if use_log: logger.info(f"loss is nan: {math.isnan(loss.item())}")
            losses.append(loss.item())
            if use_log: logger.info(f"loss appended")
            #losses.append(loss.data[0])
            all_preds.extend(preds)
            if use_log: logger.info(f"preds: {preds}")
            all_labels.extend(temp_batch[1])        #add the labels in the batch object
            if use_log: logger.info(f"labels: {temp_batch[1]}")

    model.set_train()
    preproc.set_train()        
    if use_log: logger.info(f"set_train")

    loss = sum(losses) / len(losses)
    if use_log: logger.info(f"Avg loss: {loss}")

    results = [(preproc.decode(l), preproc.decode(p))              # decodes back to phoneme labels
               for l, p in zip(all_labels, all_preds)]
    if use_log: logger.info(f"results {results}")
    cer = speech.compute_cer(results)
    print("Dev: Loss {:.3f}, CER {:.3f}".format(loss, cer))
    if use_log: logger.info(f"CER: {cer}")

    return loss, cer

def run(config, use_log, log_path):

    if use_log: 
        # create logger
        logger = logging.getLogger("train_log")
        logger.setLevel(logging.DEBUG)
        # create file handler which logs even debug messages
        fh = logging.FileHandler(log_path+".log")
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', "%Y-%m-%d %H:%M:%S")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    else:
        logger = None

    opt_cfg = config["optimizer"]
    data_cfg = config["data"]
    preproc_cfg = config["preproc"]
    model_cfg = config["model"]

    # Loaders
    batch_size = opt_cfg["batch_size"]
    preproc = loader.Preprocessor(data_cfg["train_set"], preproc_cfg, logger, 
                  start_and_end=data_cfg["start_and_end"])
    train_ldr = loader.make_loader(data_cfg["train_set"],
                        preproc, batch_size)
    dev_ldr = loader.make_loader(data_cfg["dev_set"],
                        preproc, batch_size)

    # Model
    model_class = eval("models." + model_cfg["class"])
    model = model_class(preproc.input_dim,
                        preproc.vocab_size,
                        model_cfg)
    if model_cfg["load_trained"]:
        model = load_from_trained(model, model_cfg)
        print("Succesfully loaded weights from trained model")
    model.cuda() if use_cuda else model.cpu()

    # Optimizer
    optimizer = torch.optim.SGD(model.parameters(),
                    lr=opt_cfg["learning_rate"],
                    momentum=opt_cfg["momentum"])

    if use_log: logger.info(f"====== Model, loaders, optimimzer created =======")
    if use_log: logger.info(f"model: {model}")
    if use_log: logger.info(f"preproc: {preproc}")
    if use_log: logger.info(f"optimizer: {optimizer}")



    run_state = (0, 0)
    best_so_far = float("inf")
    for e in range(opt_cfg["epochs"]):
        start = time.time()
        
        run_state = run_epoch(model, optimizer, train_ldr, logger, *run_state)
        if use_log: logger.info(f"====== Run_state finished =======") 
        if use_log: logger.info(f"preproc type: {type(preproc)}")

        msg = "Epoch {} completed in {:.2f} (s)."
        print(msg.format(e, time.time() - start))
        if use_log: logger.info(msg.format(e, time.time() - start))


        dev_loss, dev_cer = eval_dev(model, dev_ldr, preproc, logger)
        if use_log: logger.info(f"====== eval_dev finished =======")

        # Log for tensorboard
        tb.log_value("dev_loss", dev_loss, e)
        tb.log_value("dev_cer", dev_cer, e)

        if use_log: preproc.logger = None
        speech.save(model, preproc, config["save_path"])
        if use_log: logger.info(f"====== model saved =======")

        # Save the best model on the dev set
        if dev_cer < best_so_far:
            best_so_far = dev_cer
            speech.save(model, preproc,
                    config["save_path"], tag="best")
        if use_log: preproc.logger = logger
               

def load_from_trained(model, model_cfg):
    """
        loads the model with pretrained weights from the model in
        model_cfg["trained_path"]
        Arguments:
            model (torch model)
            model_cfg (dict)
    """

    trained_model = torch.load(model_cfg["trained_path"], map_location=torch.device('cpu'))
    trained_state_dict = trained_model.state_dict()
    trained_state_dict = filter_state_dict(trained_state_dict, remove_layers=model_cfg["remove_layers"])
    model_state_dict = model.state_dict()
    model_state_dict.update(trained_state_dict)
    model.load_state_dict(model_state_dict)
    return model


def filter_state_dict(state_dict, remove_layers=[]):
    """
        filters the inputted state_dict by removing the layers specified
        in remove_layers
        Arguments:
            state_dict (OrderedDict): state_dict of pytorch model
            remove_layers (list(str)): list of layers to remove 
    """

    state_dict = OrderedDict(
        {key:value for key,value in state_dict.items() 
        if key not in remove_layers}
        )
    return state_dict

def check_nan(model):
    """
        checks an iterator of training inputs if any of them have nan values
    """
    for param in model.parameters():
        if (param!=param).any():
            return True
    
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
            description="Train a speech model.")

    parser.add_argument("config",
        help="A json file with the training configuration.")
    parser.add_argument("--deterministic", default=False,
        action="store_true",
        help="Run in deterministic mode (no cudnn). Only works on GPU.")
    parser.add_argument("--use-log", default=False, action="store_true",
        help="Use a logger to store the calling of commands.")
    parser.add_argument("--log-path", type=str, default='train-log',
        help="Path to save log file.")
    args = parser.parse_args()

    with open(args.config, 'r') as fid:
        config = json.load(fid)

    random.seed(config["seed"])
    torch.manual_seed(config["seed"])

    tb.configure(config["save_path"])

    use_cuda = torch.cuda.is_available()

    if use_cuda and args.deterministic:
        torch.backends.cudnn.enabled = False
    run(config, args.use_log, args.log_path)
