from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import numpy as np
import random
import scipy.signal
import torch
import torch.autograd as autograd
import torch.utils.data as tud
import matplotlib.pyplot as plt

from speech.utils import wave

class Preprocessor():

    END = "</s>"
    START = "<s>"

    def __init__(self, data_json, max_samples=100, start_and_end=True):
        """
        Builds a preprocessor from a dataset.
        Arguments:
            data_json (string): A file containing a json representation
                of each example per line.
            max_samples (int): The maximum number of examples to be used
                in computing summary statistics.
            start_and_end (bool): Include start and end tokens in labels.
        """
        data = read_data_json(data_json)

        # Compute data mean, std from sample
        audio_files = [d['audio'] for d in data]
        random.shuffle(audio_files)
        # the mean and std are of the log of the spectogram of the audio files
        self.mean, self.std = compute_mean_std(audio_files[:max_samples])
        self._input_dim = self.mean.shape[0]

        # Make char map
        chars = list(set(t for d in data for t in d['text']))
        if start_and_end:
            # START must be last so it can easily be
            # excluded in the output classes of a model.
            chars.extend([self.END, self.START])
        self.start_and_end = start_and_end
        self.int_to_char = dict(enumerate(chars))
        self.char_to_int = {v : k for k, v in self.int_to_char.items()}

    def encode(self, text):
        text = list(text)
        if self.start_and_end:
            text = [self.START] + text + [self.END]
        return [self.char_to_int[t] for t in text]

    def decode(self, seq):
        text = [self.int_to_char[s] for s in seq]
        if not self.start_and_end:
            return text

        s = text[0] == self.START
        e = len(text)
        if text[-1] == self.END:
            e = text.index(self.END)
        return text[s:e]

    def preprocess(self, wave_file, text):
        inputs = log_specgram_from_file(wave_file)
        # print(f"log spec size: {inputs.shape}")
        inputs = (inputs - self.mean) / self.std
        targets = self.encode(text)
        return inputs, targets

    @property
    def input_dim(self):
        return self._input_dim

    @property
    def vocab_size(self):
        return len(self.int_to_char)

def compute_mean_std(audio_files):
    samples = [log_specgram_from_file(af)
               for af in audio_files]
    samples = np.vstack(samples)
    mean = np.mean(samples, axis=0)
    std = np.std(samples, axis=0)
    return mean, std

class AudioDataset(tud.Dataset):

    def __init__(self, data_json, preproc, batch_size):

        data = read_data_json(data_json)        #loads the data_json into a list
        print(f"data[0]: {data[0]}")
        self.preproc = preproc                  # assign the preproc object

        # I'm not fully certain what is going on here
        bucket_diff = 4                         # number of different buckets
        max_len = max(len(x['text']) for x in data) # max number of phoneme labels in data
        num_buckets = max_len // bucket_diff        # the number of buckets
        buckets = [[] for _ in range(num_buckets)]  # creating an empy list for the buckets
        for d in data:                          
            bid = min(len(d['text']) // bucket_diff, num_buckets - 1)
            buckets[bid].append(d)

        # Sort by input length followed by output length
        sort_fn = lambda x : (round(x['duration'], 1),
                              len(x['text']))
        for b in buckets:
            b.sort(key=sort_fn)
        
        # unpack the data in the buckets into a list
        data = [d for b in buckets for d in b]
        print(f"len of data: {len(data)}")
        self.data = data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        datum = self.data[idx]
        datum = self.preproc.preprocess(datum["audio"],
                                        datum["text"])
        return datum


class BatchRandomSampler(tud.sampler.Sampler):
    """
    Batches the data consecutively and randomly samples
    by batch without replacement.
    """

    def __init__(self, data_source, batch_size):
        
        if len(data_source) < batch_size:
            raise ValueError("batch_size is greater than data length")

        it_end = len(data_source) - batch_size + 1
        print(f"it_end: {it_end}")
        self.batches = [range(i, i + batch_size)
                for i in range(0, it_end, batch_size)]
        print(f"self.batches: {self.batches}")
        self.data_source = data_source

    def __iter__(self):
        random.shuffle(self.batches)
        return (i for b in self.batches for i in b)

    def __len__(self):
        return len(self.data_source)

def make_loader(dataset_json, preproc,
                batch_size, num_workers=4):
    dataset = AudioDataset(dataset_json, preproc,
                           batch_size)
    #print(f"dataset: {[i for i in dataset]}")
    sampler = BatchRandomSampler(dataset, batch_size)
    print(f"sampler: {[i for i in sampler]}")
    loader = tud.DataLoader(dataset,
                batch_size=batch_size,
                sampler=sampler,
                num_workers=num_workers,
                collate_fn=lambda batch : zip(*batch),
                drop_last=True)
    return loader

def log_specgram_from_file(audio_file: str, channel: int=0, plot=False):
    """Computes the log of the spectrogram from from a input audio file string

    Arguments
    ----------
        audio_file: str, the filename of the audio file
        channel: int, zero-indexed optional keyword argument specifying the channel to use
        plot: bool, if true a plot of the spectrogram will be generated

    Returns
    -------
        np.ndarray, the transposed log of the spectrogram as returned by log_specgram
    """
    
    audio, sr = wave.array_from_wave(audio_file)
    print(f"audio_file: {audio_file}")
    print(f"audio shape: {audio.shape}, sample rate {sr}")

    if len(audio.shape)>1:     # there are multiple channels
        _, num_channels = audio.shape
        print(f"are audio channels empty: channel 0: {sum(audio[:,0])==0}, channel 1: {sum(audio[:,1])==0}")
        assert channel <= num_channels, "channel argument greater than audio channels"
        audio = audio[:,channel]
   
    return log_specgram(audio, sr, plot=plot)

def log_specgram(audio, sample_rate, window_size=20,
                 step_size=10, eps=1e-10, plot=False):
    nperseg = int(window_size * sample_rate / 1e3)
    noverlap = int(step_size * sample_rate / 1e3)
    print(f"nperseg: {nperseg}, noverlap: {noverlap}, sample_rate: {sample_rate}")
    f, t, spec = scipy.signal.spectrogram(audio,
                    fs=sample_rate,
                    window='hann',
                    nperseg=nperseg,
                    noverlap=noverlap,
                    detrend=False)
    print(f"log spectrogram shape: {spec.shape}, f.shape:{f.shape}, t.shape: {t.shape}")
    if plot==True:
        plot_spectrogram(f,t, spec)
    return np.log(spec.T.astype(np.float32) + eps)


def compare_log_spec_from_file(audio_file_1: str, audio_file_2: str, plot=False):
    """This function takes in two audio paths and calculates the difference between the spectrograms 
        by subtracting them. 

    """
    audio_1, sr_1 = wave.array_from_wave(audio_file_1)
    audio_2, sr_2 = wave.array_from_wave(audio_file_2)

    if len(audio_1.shape)>1:
        audio_1 = audio_1[:,0]  # take the first channel
    if len(audio_2.shape)>1:
        audio_2 = audio_2[:,0]  # take the first channel
    
    window_size = 20
    step_size = 10

    nperseg_1 = int(window_size * sr_1 / 1e3)
    noverlap_1 = int(step_size * sr_1 / 1e3)

    print(f"nperseg_1:{nperseg_1}, noverlap_1:{noverlap_1}")

    nperseg_2 = int(window_size * sr_2 / 1e3)
    noverlap_2 = int(step_size * sr_2 / 1e3)

    freq_1, time_1, spec_1 = scipy.signal.spectrogram(audio_1,
                    fs=sr_1,
                    window='hann',
                    nperseg=nperseg_1,
                    noverlap=noverlap_1,
                    detrend=False)

    freq_2, time_2, spec_2 = scipy.signal.spectrogram(audio_2,
                    fs=sr_2,
                    window='hann',
                    nperseg=nperseg_2,
                    noverlap=noverlap_2,
                    detrend=False)
    
    spec_diff = spec_1 - spec_2 
    freq_diff = freq_1 - freq_2
    time_diff = time_1 - time_2

    if plot:
        plot_spectrogram(freq_diff, time_diff, spec_diff)
        #plot_spectrogram(freq_1, time_1, spec_2)
        #plot_spectrogram(freq_2, time_2, spec_2)

    print(f"sum of spectrogram difference: {np.sum(spec_diff)}")
    
    return spec_diff


def plot_spectrogram(f, t, Sxx):
    """This function plots a spectrogram using matplotlib

    Arguments
    ----------
    f: the frequency output of the scipy.signal.spectrogram
    t: the time series output of the scipy.signal.spectrogram
    Sxx: the spectrogram output of scipy.signal.spectrogram

    Returns
    --------
    None

    Note: the function scipy.signal.spectrogram returns f, t, Sxx in that order
    """
    plt.pcolormesh(t, f, Sxx)
    plt.ylabel('Frequency [Hz]')
    plt.xlabel('Time [sec]')
    plt.show()

def read_data_json(data_json):
    with open(data_json) as fid:
        return [json.loads(l) for l in fid]
