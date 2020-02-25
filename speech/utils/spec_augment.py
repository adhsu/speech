# Copyright 2019 RnD at Spoon Radio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""SpecAugment Implementation for Tensorflow.
Related paper : https://arxiv.org/pdf/1904.08779.pdf
In this paper, show summarized parameters by each open datasets in Tabel 1.
-----------------------------------------
Policy | W  | F  | m_F |  T  |  p  | m_T
-----------------------------------------
None   |  0 |  0 |  -  |  0  |  -  |  -
-----------------------------------------
LB     | 80 | 27 |  1  | 100 | 1.0 | 1
-----------------------------------------
LD     | 80 | 27 |  2  | 100 | 1.0 | 2
-----------------------------------------
SM     | 40 | 15 |  2  |  70 | 0.2 | 2
-----------------------------------------
SS     | 40 | 27 |  2  |  70 | 0.2 | 2
-----------------------------------------
LB : LibriSpeech basic
LD : LibriSpeech double
SM : Switchboard mild
SS : Switchboard strong
"""

import librosa
import librosa.display
import numpy as np
import random
import matplotlib
#matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from .sparse_image_warp import sparse_image_warp
import torch


def time_warp(spec, W):
    
    if W==0:
        return spec

    num_rows = spec.shape[1]
    spec_len = spec.shape[2]

    assert spec_len>2*W, "frequency dimension is not large enough for W parameter"
    assert num_rows>0, "time dimension must be greater than zero"

    y = num_rows // 2
    horizontal_line_at_ctr = spec[0][y]
    # assert len(horizontal_line_at_ctr) == spec_len

    point_to_warp = horizontal_line_at_ctr[random.randrange(W, spec_len-W)]
    # assert isinstance(point_to_warp, torch.Tensor)

    # Uniform distribution from (0,W) with chance to be up to W negative
    dist_to_warp = random.randrange(-W, W)
    
    #print(f"W is: {W}")
    #print(f"point_to_warp: {point_to_warp}")
    #print(f"dist_to_warp: {dist_to_warp}")

    src_pts = torch.tensor([[[y, point_to_warp]]])
    dest_pts = torch.tensor([[[y, point_to_warp + dist_to_warp]]])
    warped_spectro, dense_flows = sparse_image_warp(spec, src_pts, dest_pts)

    return warped_spectro.squeeze(3)


def spec_augment(mel_spectrogram, time_warping_para=5, frequency_masking_para=50,
                 time_masking_para=50, frequency_mask_num=1, time_mask_num=1):
    """Spec augmentation Calculation Function.
    'SpecAugment' have 3 steps for audio data augmentation.
    first step is time warping using Tensorflow's image_sparse_warp function.
    Second step is frequency masking, last step is time masking.
    # Arguments:
      spectrogram(torch tensor): audio file path of you want to warping and masking.
      time_warping_para(float): Augmentation parameter, "time warp parameter W".
        If none, default = 40.
      frequency_masking_para(float): Augmentation parameter, "frequency mask parameter F"
        If none, default = 27.
      time_masking_para(float): Augmentation parameter, "time mask parameter T"
        If none, default = 70.
      frequency_mask_num(float): number of frequency masking lines, "m_F".
        If none, default = 1.
      time_mask_num(float): number of time masking lines, "m_T".
        If none, default = 1.
    # Returns
      mel_spectrogram(numpy array): warped and masked mel spectrogram.
    """
    mel_spectrogram = mel_spectrogram.unsqueeze(0)

    v = mel_spectrogram.shape[1]
    tau = mel_spectrogram.shape[2]
    #print(f" nu is: {v}")
    #print(f"tau is: {tau}")

    # Step 1 : Time warping
    warped_mel_spectrogram = time_warp(mel_spectrogram, W=time_warping_para)

    # Step 2 : Frequency masking
    for i in range(frequency_mask_num):
        f = np.random.uniform(low=0.0, high=frequency_masking_para)
        f = int(f)
        if v - f < 0:
            continue
        f0 = random.randint(0, v-f)
        #print(f"f is: {f} at: {f0}")

        warped_mel_spectrogram[:, f0:f0+f, :] = 0

    # Step 3 : Time masking
    for i in range(time_mask_num):
        t = np.random.uniform(low=0.0, high=time_masking_para)
        t = int(t)

        if tau - t < 0:
            continue
        t0 = random.randint(0, tau-t)
        #print(f"t is: {t} at: {t0}")

        warped_mel_spectrogram[:, :, t0:t0+t] = 0

    return warped_mel_spectrogram.squeeze()


def visualization_spectrogram(mel_spectrogram, title, ax=None):
    """visualizing result of SpecAugment
    # Arguments:
      spectrogram(ndarray): mel_spectrogram to visualize.
      title(String): plot figure's title
    """
    #mel_spectrogram = mel_spectrogram.unsqueeze(0)
    # Show mel-spectrogram using librosa's specshow.

    #plt.figure(figsize=(10, 4))
    librosa.display.specshow(
            mel_spectrogram,
            y_axis='log',x_axis='time', sr=32000, ax=ax
            )
    # plt.colorbar(format='%+2.0f dB')
    
    plt.title(title) if ax==None else ax.set_title(title) 
    #plt.tight_layout()
    #plt.show()
