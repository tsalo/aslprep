"""Functions for evaluating quality of ASL derivatives."""
import nibabel as nb
import numpy as np
from nibabel.processing import smooth_image
from scipy.stats import gmean


def dice(input1, input2):
    """Compute Dice coefficient between the binary objects in two images.

    Parameters
    ----------
    input1 : str
        Input data containing objects. Can be any type but will be converted
        into binary: background where 0, object everywhere else.
    input2 : str
        Input data containing objects. Can be any type but will be converted
        into binary: background where 0, object everywhere else.

    Returns
    -------
    coef : float
        The Dice coefficient between the object(s) in ```input1``` and the
        object(s) in ```input2```. It ranges from 0 (no overlap) to 1 (perfect overlap).
    """
    input1 = nb.load(input1).get_fdata()
    input2 = nb.load(input2).get_fdata()
    input1 = np.atleast_1d(input1.astype(bool))
    input2 = np.atleast_1d(input2.astype(bool))

    intersection = np.count_nonzero(input1 & input2)

    size_i1 = np.count_nonzero(input1)
    size_i2 = np.count_nonzero(input2)

    try:
        coef = 2.0 * intersection / float(size_i1 + size_i2)
    except ZeroDivisionError:
        coef = 0.0

    return coef


def jaccard(input1, input2):
    """Compute Jaccard coefficient between the binary objects in two images.

    Parameters
    ----------
    input1 : str
        Input data containing objects. Can be any type but will be converted
        into binary: background where 0, object everywhere else.
    input2 : str
        Input data containing objects. Can be any type but will be converted
        into binary: background where 0, object everywhere else.

    Returns
    -------
    coef : float
        The Jaccard coefficient between the object(s) in `input1` and the
        object(s) in `input2`. It ranges from 0 (no overlap) to 1 (perfect overlap).
    """
    input1 = nb.load(input1).get_fdata()
    input2 = nb.load(input2).get_fdata()
    input1 = np.atleast_1d(input1.astype(bool))
    input2 = np.atleast_1d(input2.astype(bool))

    intersection = np.count_nonzero(input1 & input2)
    union = np.count_nonzero(input1 | input2)

    coef = float(intersection) / float(union)

    return coef


def crosscorr(input1, input2):
    """Compute cross correlation between two binary images."""
    input1 = nb.load(input1).get_fdata()
    input2 = nb.load(input2).get_fdata()
    input1 = np.atleast_1d(input1.astype(bool)).flatten()
    input2 = np.atleast_1d(input2.astype(bool)).flatten()
    cc = np.corrcoef(input1, input2)[0][1]
    return cc


def coverage(input1, input2):
    """Estimate the coverage between two binary images."""
    input1 = nb.load(input1).get_fdata()
    input2 = nb.load(input2).get_fdata()
    input1 = np.atleast_1d(input1.astype(bool))
    input2 = np.atleast_1d(input2.astype(bool))
    intsec = np.count_nonzero(input1 & input2)
    if np.sum(input1) > np.sum(input2):
        smallv = np.sum(input2)
    else:
        smallv = np.sum(input1)
    cov = float(intsec) / float(smallv)
    return cov


def globalcbf(cbf, gm, wm, csf, thresh=0.7):
    """Compute global measures of quality, whatever that is."""
    cbf = nb.load(cbf).get_fdata()
    gm = nb.load(gm).get_fdata()
    wm = nb.load(wm).get_fdata()
    csf = nb.load(csf).get_fdata()
    b1 = gm < thresh
    gm[b1] = 0
    bx = cbf[gm > 0]
    b2 = wm < thresh
    wm[b2] = 0
    by = cbf[wm > 0]
    b3 = csf < thresh
    csf[b3] = 0
    bz = cbf[csf > 0]
    return np.mean(bx), np.mean(by), np.mean(bz)


def cbf_qei(gm, wm, csf, img, thresh=0.8):
    """Compute quality evaluation index (QEI) of CBF.

    The QEI is based on :footcite:t:`cbfqc`.

    References
    ----------
    .. footbibliography
    """

    def fun1(x, xdata):
        d1 = np.exp(-(x[0]) * np.power(xdata, x[1]))
        return d1

    def fun2(x, xdata):
        d1 = 1 - np.exp(-(x[0]) * np.power(xdata, x[1]))
        return d1

    x1 = [0.054, 0.9272]
    x2 = [2.8478, 0.5196]
    x4 = [3.0126, 2.4419]
    scbf = smooth_image(nb.load(img), fwhm=5).get_fdata()
    if len(scbf.shape) > 3:
        scbf = scbf[:, :, :, 0]
    # load prob maps
    gmm = nb.load(gm).get_fdata()
    wmm = nb.load(wm).get_fdata()
    ccf = nb.load(csf).get_fdata()
    if len(gmm.shape) > 3:
        gmm = gmm[:, :, :, 0]
        wmm = wmm[:, :, :, 0]
        ccf = ccf[:, :, :, 0]
    pbcf = 2.5 * gmm + wmm  # gmm is 2.5 times wm
    msk = np.array((scbf != 0) & (scbf != np.nan) & (pbcf != np.nan)).astype(int)

    gm1 = np.array(gmm > thresh)
    wm1 = np.array(wmm > thresh)
    cc1 = np.array(ccf > thresh)
    r1 = np.array([0, np.corrcoef(scbf[msk == 1], pbcf[msk == 1])[1, 0]]).max()

    V = (
        (np.sum(gm1) - 1) * np.var(scbf[gm1 > 0])
        + (np.sum(wm1) - 1) * np.var(scbf[wm1 > 0])
        + (np.sum(cc1) - 1) * np.var(scbf[cc1 > 0])
    ) / (np.sum(gm1 > 0) + np.sum(wm1 > 0) + np.sum(cc1 > 0) - 3)

    negGM = np.sum(scbf[gm1] < 0) / (np.sum(gm1))
    GMCBF = np.mean(scbf[gm1])
    CV = V / np.abs(GMCBF)
    Q = [fun1(x1, CV), fun1(x2, negGM), fun2(x4, r1)]
    return gmean(Q)


def negativevoxel(cbf, gm, thresh=0.7):
    """Compute percentage of negative voxels within grey matter mask."""
    gm = nb.load(gm).get_fdata()
    cbf = nb.load(cbf).get_fdata()
    gm1 = np.array(gm > thresh)
    gm1[gm1 > 0] = 1
    npgm = np.sum(gm1)
    cbfgm = np.array(cbf < 0)
    cbfgm[cbfgm < 0] = 1
    ncbfgm = np.sum(np.multiply(cbfgm, gm1))
    pernegcbf = np.multiply(np.divide(ncbfgm, npgm), 100)
    return pernegcbf