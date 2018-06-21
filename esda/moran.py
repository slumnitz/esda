"""
Moran's I Spatial Autocorrelation Statistics

"""
__author__ = "Sergio J. Rey <srey@asu.edu>, \
        Dani Arribas-Bel <daniel.arribas.bel@gmail.com>"
from libpysal.weights.spatial_lag import lag_spatial as slag
from .smoothing import assuncao_rate
from .tabular import _univariate_handler, _bivariate_handler
import scipy.stats as stats
import numpy as np

__all__ = ["Moran", "Moran_Local", "Moran_BV", "Moran_BV_matrix",
           "Moran_Local_BV", "Moran_Rate", "Moran_Local_Rate"]

PERMUTATIONS = 999


class Moran(object):
    """Moran's I Global Autocorrelation Statistic

    Parameters
    ----------

    y               : array
                      variable measured across n spatial units
    w               : W
                      spatial weights instance
    transformation  : string
                      weights transformation,  default is row-standardized "r".
                      Other options include "B": binary,  "D":
                      doubly-standardized,  "U": untransformed
                      (general weights), "V": variance-stabilizing.
    permutations    : int
                      number of random permutations for calculation of
                      pseudo-p_values
    two_tailed      : boolean
                      If True (default) analytical p-values for Moran are two
                      tailed, otherwise if False, they are one-tailed.

    Attributes
    ----------
    y            : array
                   original variable
    w            : W
                   original w object
    permutations : int
                   number of permutations
    I            : float
                   value of Moran's I
    EI           : float
                   expected value under normality assumption
    VI_norm      : float
                   variance of I under normality assumption
    seI_norm     : float
                   standard deviation of I under normality assumption
    z_norm       : float
                   z-value of I under normality assumption
    p_norm       : float
                   p-value of I under normality assumption
    VI_rand      : float
                   variance of I under randomization assumption
    seI_rand     : float
                   standard deviation of I under randomization assumption
    z_rand       : float
                   z-value of I under randomization assumption
    p_rand       : float
                   p-value of I under randomization assumption
    two_tailed   : boolean
                   If True p_norm and p_rand are two-tailed, otherwise they
                   are one-tailed.
    sim          : array
                   (if permutations>0)
                   vector of I values for permuted samples
    p_sim        : array
                   (if permutations>0)
                   p-value based on permutations (one-tailed)
                   null: spatial randomness
                   alternative: the observed I is extreme if
                   it is either extremely greater or extremely lower
                   than the values obtained based on permutations
    EI_sim       : float
                   (if permutations>0)
                   average value of I from permutations
    VI_sim       : float
                   (if permutations>0)
                   variance of I from permutations
    seI_sim      : float
                   (if permutations>0)
                   standard deviation of I under permutations.
    z_sim        : float
                   (if permutations>0)
                   standardized I based on permutations
    p_z_sim      : float
                   (if permutations>0)
                   p-value based on standard normal approximation from
                   permutations

    Examples
    --------
    >>> import libpysal.api as lps
    >>> w = lps.open(lps.get_path("stl.gal")).read()
    >>> f = lps.open(lps.get_path("stl_hom.txt"))
    >>> y = np.array(f.by_col['HR8893'])
    >>> from esda.moran import Moran
    >>> mi = Moran(y,  w)
    >>> round(mi.I, 3)
    0.244
    >>> mi.EI
    -0.012987012987012988
    >>> mi.p_norm
    0.00027147862770937614

    SIDS example replicating OpenGeoda
    >>> w = lps.open(lps.get_path("sids2.gal")).read()
    >>> f = lps.open(lps.get_path("sids2.dbf"))
    >>> SIDR = np.array(f.by_col("SIDR74"))
    >>> mi = Moran(SIDR,  w)
    >>> round(mi.I, 3)
    0.248
    >>> mi.p_norm
    0.0001158330781489969

    One-tailed

    >>> mi_1 = Moran(SIDR,  w, two_tailed=False)
    >>> round(mi_1.I, 3)
    0.248
    >>> round(mi_1.p_norm, 4)
    0.0001

    """
    def __init__(self, y, w, transformation="r", permutations=PERMUTATIONS,
                 two_tailed=True):
        y = np.asarray(y).flatten()
        self.y = y
        w.transform = transformation
        self.w = w
        self.permutations = permutations
        self.__moments()
        self.I = self.__calc(self.z)
        self.z_norm = (self.I - self.EI) / self.seI_norm
        self.z_rand = (self.I - self.EI) / self.seI_rand

        if self.z_norm > 0:
            self.p_norm = 1 - stats.norm.cdf(self.z_norm)
            self.p_rand = 1 - stats.norm.cdf(self.z_rand)
        else:
            self.p_norm = stats.norm.cdf(self.z_norm)
            self.p_rand = stats.norm.cdf(self.z_rand)

        if two_tailed:
            self.p_norm *= 2.
            self.p_rand *= 2.

        if permutations:
            sim = [self.__calc(np.random.permutation(self.z))
                   for i in range(permutations)]
            self.sim = sim = np.array(sim)
            above = sim >= self.I
            larger = above.sum()
            if (self.permutations - larger) < larger:
                larger = self.permutations - larger
            self.p_sim = (larger + 1.) / (permutations + 1.)
            self.EI_sim = sim.sum() / permutations
            self.seI_sim = np.array(sim).std()
            self.VI_sim = self.seI_sim ** 2
            self.z_sim = (self.I - self.EI_sim) / self.seI_sim
            if self.z_sim > 0:
                self.p_z_sim = 1 - stats.norm.cdf(self.z_sim)
            else:
                self.p_z_sim = stats.norm.cdf(self.z_sim)

        # provide .z attribute that is znormalized
        sy = y.std()
        self.z /= sy
        
    def __moments(self):
        self.n = len(self.y)
        y = self.y
        z = y - y.mean()
        self.z = z
        self.z2ss = (z * z).sum()
        self.EI = -1. / (self.n - 1)
        n = self.n
        n2 = n * n
        s1 = self.w.s1
        s0 = self.w.s0
        s2 = self.w.s2
        s02 = s0 * s0
        v_num = n2 * s1 - n * s2 + 3 * s02 
        v_den = (n - 1) * (n + 1) * s02
        self.VI_norm = v_num / v_den - (1.0 / (n - 1)) ** 2
        self.seI_norm = self.VI_norm ** (1 / 2.)

        # variance under randomization
        xd4 = z**4
        xd2 = z**2
        k_num = xd4.sum() / n
        k_den = (xd2.sum() / n)**2
        k = k_num / k_den
        EI = self.EI
        A = n * ((n2 - 3 * n + 3) * s1 - n * s2 + 3 * s02)
        B = k * ((n2 - n) * s1 - 2 * n * s2 + 6 * s02  )
        VIR = (A - B) / ((n - 1) * (n - 2) * (n - 3 ) * s02) - EI*EI
        self.VI_rand = VIR 
        self.seI_rand = VIR ** (1 / 2.)

    def __calc(self, z):
        zl = slag(self.w, z)
        inum = (z * zl).sum()
        return self.n / self.w.s0 * inum / self.z2ss

    @property
    def _statistic(self):
        """More consistent hidden attribute to access ESDA statistics"""
        return self.I

    @classmethod
    def by_col(cls, df, cols, w=None, inplace=False, pvalue='sim', outvals=None, **stat_kws):
        """
        Function to compute a Moran statistic on a dataframe

        Arguments
        ---------
        df          :   pandas.DataFrame
                        a pandas dataframe with a geometry column
        cols        :   string or list of string
                        name or list of names of columns to use to compute the statistic
        w           :   pysal weights object
                        a weights object aligned with the dataframe. If not provided, this
                        is searched for in the dataframe's metadata
        inplace     :   bool
                        a boolean denoting whether to operate on the dataframe inplace or to
                        return a series contaning the results of the computation. If
                        operating inplace, the derived columns will be named
                        'column_moran'
        pvalue      :   string
                        a string denoting which pvalue should be returned. Refer to the
                        the Moran statistic's documentation for available p-values
        outvals     :   list of strings
                        list of arbitrary attributes to return as columns from the
                        Moran statistic
        **stat_kws  :   keyword arguments
                        options to pass to the underlying statistic. For this, see the
                        documentation for the Moran statistic.

        Returns
        --------
        If inplace, None, and operation is conducted on dataframe in memory. Otherwise,
        returns a copy of the dataframe with the relevant columns attached.

        See Also
        ---------
        For further documentation, refer to the Moran class in pysal.esda
        """
        return _univariate_handler(df, cols, w=w, inplace=inplace, pvalue=pvalue,
                                   outvals=outvals, stat=cls,
                                   swapname=cls.__name__.lower(), **stat_kws)

class Moran_BV(object):
    """
    Bivariate Moran's I

    Parameters
    ----------
    x : array
        x-axis variable
    y : array
        wy will be on y axis
    w : W
        weight instance assumed to be aligned with y
    transformation  : {'R', 'B', 'D', 'U', 'V'}
                      weights transformation, default is row-standardized "r".
                      Other options include
                      "B": binary,
                      "D": doubly-standardized,
                      "U": untransformed (general weights),
                      "V": variance-stabilizing.
    permutations    : int
                      number of random permutations for calculation of pseudo
                      p_values

    Attributes
    ----------
    zx            : array
                    original x variable standardized by mean and std
    zy            : array
                    original y variable standardized by mean and std
    w             : W
                    original w object
    permutation   : int
                    number of permutations
    I             : float
                    value of bivariate Moran's I
    sim           : array
                    (if permutations>0)
                    vector of I values for permuted samples
    p_sim         : float
                    (if permutations>0)
                    p-value based on permutations (one-sided)
                    null: spatial randomness
                    alternative: the observed I is extreme
                    it is either extremely high or extremely low
    EI_sim        : array
                    (if permutations>0)
                    average value of I from permutations
    VI_sim        : array
                    (if permutations>0)
                    variance of I from permutations
    seI_sim       : array
                    (if permutations>0)
                    standard deviation of I under permutations.
    z_sim         : array
                    (if permutations>0)
                    standardized I based on permutations
    p_z_sim       : float
                    (if permutations>0)
                    p-value based on standard normal approximation from
                    permutations

    Notes
    -----

    Inference is only based on permutations as analytical results are not too
    reliable.

    Examples
    --------
    >>> import libpysal.api as lps
    >>> import numpy as np

    Set random number generator seed so we can replicate the example

    >>> np.random.seed(10)

    Open the sudden infant death dbf file and read in rates for 74 and 79
    converting each to a numpy array

    >>> f = lps.open(lps.get_path("sids2.dbf"))
    >>> SIDR74 = np.array(f.by_col['SIDR74'])
    >>> SIDR79 = np.array(f.by_col['SIDR79'])

    Read a GAL file and construct our spatial weights object

    >>> w = lps.open(lps.get_path("sids2.gal")).read()

    Create an instance of Moran_BV
    >>> from esda.moran import Moran_BV
    >>> mbi = Moran_BV(SIDR79,  SIDR74,  w)

    What is the bivariate Moran's I value

    >>> round(mbi.I, 3)
    0.156

    Based on 999 permutations, what is the p-value of our statistic

    >>> round(mbi.p_z_sim, 3)
    0.001


    """
    def __init__(self, x, y, w, transformation="r", permutations=PERMUTATIONS):
        x = np.asarray(x).flatten()
        y = np.asarray(y).flatten()
        zy = (y - y.mean()) / y.std(ddof=1)
        zx = (x - x.mean()) / x.std(ddof=1)
        self.y = y
        self.x = x
        self.zx = zx
        self.zy = zy
        n = x.shape[0]
        self.den = n - 1.  # zx'zx = zy'zy = n-1
        w.transform = transformation
        self.w = w
        self.I = self.__calc(zy)
        if permutations:
            nrp = np.random.permutation
            sim = [self.__calc(nrp(zy)) for i in range(permutations)]
            self.sim = sim = np.array(sim)
            above = sim >= self.I
            larger = above.sum()
            if (permutations - larger) < larger:
                larger = permutations - larger
            self.p_sim = (larger + 1.) / (permutations + 1.)
            self.EI_sim = sim.sum() / permutations
            self.seI_sim = np.array(sim).std()
            self.VI_sim = self.seI_sim ** 2
            self.z_sim = (self.I - self.EI_sim) / self.seI_sim
            if self.z_sim > 0:
                self.p_z_sim = 1 - stats.norm.cdf(self.z_sim)
            else:
                self.p_z_sim = stats.norm.cdf(self.z_sim)

    def __calc(self, zy):
        wzy = slag(self.w, zy)
        self.num = (self.zx * wzy).sum()
        return self.num / self.den

    @property
    def _statistic(self):
        """More consistent hidden attribute to access ESDA statistics"""
        return self.I

    @classmethod
    def by_col(cls, df, x, y=None, w=None, inplace=False, pvalue='sim', outvals=None, **stat_kws):
        """
        Function to compute a Moran_BV statistic on a dataframe

        Arguments
        ---------
        df          :   pandas.DataFrame
                        a pandas dataframe with a geometry column
        X           :   list of strings
                        column name or list of column names to use as X values to compute
                        the bivariate statistic. If no Y is provided, pairwise comparisons
                        among these variates are used instead.
        Y           :   list of strings
                        column name or list of column names to use as Y values to compute
                        the bivariate statistic. if no Y is provided, pariwise comparisons
                        among the X variates are used instead.
        w           :   pysal weights object
                        a weights object aligned with the dataframe. If not provided, this
                        is searched for in the dataframe's metadata
        inplace     :   bool
                        a boolean denoting whether to operate on the dataframe inplace or to
                        return a series contaning the results of the computation. If
                        operating inplace, the derived columns will be named
                        'column_moran_local'
        pvalue      :   string
                        a string denoting which pvalue should be returned. Refer to the
                        the Moran_BV statistic's documentation for available p-values
        outvals     :   list of strings
                        list of arbitrary attributes to return as columns from the
                        Moran_BV statistic
        **stat_kws  :   keyword arguments
                        options to pass to the underlying statistic. For this, see the
                        documentation for the Moran_BV statistic.


        Returns
        --------
        If inplace, None, and operation is conducted on dataframe in memory. Otherwise,
        returns a copy of the dataframe with the relevant columns attached.

        See Also
        ---------
        For further documentation, refer to the Moran_BV class in pysal.esda
        """
        return _bivariate_handler(df, x, y=y, w=w, inplace=inplace,
                                  pvalue = pvalue, outvals = outvals,
                                  swapname=cls.__name__.lower(), stat=cls,**stat_kws)


def Moran_BV_matrix(variables, w, permutations=0, varnames=None):
    """
    Bivariate Moran Matrix

    Calculates bivariate Moran between all pairs of a set of variables.

    Parameters
    ----------
    variables    : array or pandas.DataFrame
                   sequence of variables to be assessed
    w            : W
                   a spatial weights object
    permutations : int
                   number of permutations
    varnames     : list, optional if variables is an array
                   Strings for variable names. Will add an
                   attribute to `Moran_BV` objects in results needed for plotting
                   in `splot` or `.plot()`. Default =None.
                   Note: If variables is a `pandas.DataFrame` varnames
                   will automatically be generated
    Returns
    -------
    results      : dictionary
                   (i,  j) is the key for the pair of variables, values are
                   the Moran_BV objects.

    Examples
    --------
    Example 1: Variables passed in as an array
    
    open dbf

    >>> import libpysal.api as lps
    >>> f = lps.open(lps.get_path("sids2.dbf"))

    pull of selected variables from dbf and create numpy arrays for each

    >>> varnames = ['SIDR74',  'SIDR79',  'NWR74',  'NWR79']
    >>> vars = [np.array(f.by_col[var]) for var in varnames]

    create a contiguity matrix from an external gal file

    >>> w = lps.open(lps.get_path("sids2.gal")).read()

    create an instance of Moran_BV_matrix

    >>> from esda.moran import Moran_BV_matrix
    >>> res = Moran_BV_matrix(vars,  w,  varnames = varnames)

    check values

    >>> round(res[(0,  1)].I,7)
    0.1936261
    >>> round(res[(3,  0)].I,7)
    0.3770138


    Example 2: variables passed in as pandas.Dataframe
    
    Imports
    
    >>> import libpysal.api as lp
    >>> from libpysal import examples
    >>> import geopandas as gpd
    >>> import pandas as pd
    >>> import matplotlib.pyplot as plt
    >>> import matplotlib
    >>> import numpy as np
    >>> from splot.esda import moran_facet
    
    Prepare DataFrame
    
    >>> path = examples.get_path('columbus.shp')
    >>> gdf = gpd.read_file(path)
    >>> variables2 = gdf[['HOVAL', 'CRIME', 'INC', 'EW']]
    >>> w2 = lp.queen_from_shapefile(path)
    
    Create Moran_BV_Matrix
    
    >>> matrix = Moran_BV_matrix(variables2, w2)
    >>> matrix
    
    Plot Moran_facet using `splot`
    
    >>> moran_facet(matrix)
    >>> plt.show()
    
    """
    try:
        # check if pandas is installed
        import pandas
        if isinstance(variables, pandas.DataFrame):
            # if yes use variables as df and convert to numpy_array
            varnames = pandas.Index.tolist(variables.columns)
            variables_n = []
            for var in varnames:
                variables_n.append(variables[str(var)].values)
        else:
            variables_n = variables
    except ImportError:
        variables_n = variables
    
    results = _Moran_BV_Matrix_array(variables=variables_n, w=w,
                                     permutations=permutations,
                                     varnames=varnames)
    return results


def _Moran_BV_Matrix_array(variables, w, permutations=0, varnames=None):
    """
    Base calculation for MORAN_BV_Matrix
    """
    if varnames is None:
        varnames = ['x{}'.format(i) for i in range(k)]

    k = len(variables)
    rk = list(range(0, k - 1))
    results = {}
    for i in rk:
        for j in range(i + 1, k):
            y1 = variables[i]
            y2 = variables[j]
            results[i, j] = Moran_BV(y1, y2, w, permutations=permutations)
            results[j, i] = Moran_BV(y2, y1, w, permutations=permutations)
            results[i, j].varnames = {'x': varnames[i], 'y': varnames[j]}
            results[j, i].varnames = {'x': varnames[j], 'y': varnames[i]}
    return results


class Moran_Rate(Moran):
    """
    Adjusted Moran's I Global Autocorrelation Statistic for Rate
    Variables [Assuncao1999]_

    Parameters
    ----------

    e               : array
                      an event variable measured across n spatial units
    b               : array
                      a population-at-risk variable measured across n spatial
                      units
    w               : W
                      spatial weights instance
    adjusted        : boolean
                      whether or not Moran's I needs to be adjusted for rate
                      variable
    transformation  : {'R', 'B', 'D', 'U', 'V'}
                      weights transformation, default is row-standardized "r".
                      Other options include
                      "B": binary,
                      "D": doubly-standardized,
                      "U": untransformed (general weights),
                      "V": variance-stabilizing.
    two_tailed      : boolean
                      If True (default), analytical p-values for Moran's I are
                      two-tailed, otherwise they are one tailed.
    permutations    : int
                      number of random permutations for calculation of pseudo
                      p_values

    Attributes
    ----------
    y            : array
                   rate variable computed from parameters e and b
                   if adjusted is True, y is standardized rates
                   otherwise, y is raw rates
    w            : W
                   original w object
    permutations : int
                   number of permutations
    I            : float
                   value of Moran's I
    EI           : float
                   expected value under normality assumption
    VI_norm      : float
                   variance of I under normality assumption
    seI_norm     : float
                   standard deviation of I under normality assumption
    z_norm       : float
                   z-value of I under normality assumption
    p_norm       : float
                   p-value of I under normality assumption
    VI_rand      : float
                   variance of I under randomization assumption
    seI_rand     : float
                   standard deviation of I under randomization assumption
    z_rand       : float
                   z-value of I under randomization assumption
    p_rand       : float
                   p-value of I under randomization assumption
    two_tailed   : boolean
                   If True, p_norm and p_rand are two-tailed p-values,
                   otherwise they are one-tailed.
    sim          : array
                   (if permutations>0)
                   vector of I values for permuted samples
    p_sim        : array
                   (if permutations>0)
                   p-value based on permutations (one-sided)
                   null: spatial randomness
                   alternative: the observed I is extreme if it is
                   either extremely greater or extremely lower than the values
                   obtained from permutaitons
    EI_sim       : float
                   (if permutations>0)
                   average value of I from permutations
    VI_sim       : float
                   (if permutations>0)
                   variance of I from permutations
    seI_sim      : float
                   (if permutations>0)
                   standard deviation of I under permutations.
    z_sim        : float
                   (if permutations>0)
                   standardized I based on permutations
    p_z_sim      : float
                   (if permutations>0)
                   p-value based on standard normal approximation from

    Examples
    --------
    >>> import libpysal.api as lps
    >>> w = lps.open(lps.get_path("sids2.gal")).read()
    >>> f = lps.open(lps.get_path("sids2.dbf"))
    >>> e = np.array(f.by_col('SID79'))
    >>> b = np.array(f.by_col('BIR79'))
    >>> from esda.moran import Moran_Rate
    >>> mi = Moran_Rate(e, b,  w, two_tailed=False)
    >>> "%6.4f" % mi.I
    '0.1662'
    >>> "%6.4f" % mi.p_norm
    '0.0042'
    """

    def __init__(self, e, b, w, adjusted=True, transformation="r",
                 permutations=PERMUTATIONS, two_tailed=True):
        e = np.asarray(e).flatten()
        b = np.asarray(b).flatten()
        if adjusted:
            y = assuncao_rate(e, b)
        else:
            y = e * 1.0 / b
        Moran.__init__(self, y, w, transformation=transformation,
                       permutations=permutations, two_tailed=two_tailed)

    @classmethod
    def by_col(cls, df, events, populations, w=None, inplace=False,
               pvalue='sim', outvals=None, swapname='',  **stat_kws):
        """
        Function to compute a Moran_Rate statistic on a dataframe

        Arguments
        ---------
        df          :   pandas.DataFrame
                        a pandas dataframe with a geometry column
        events      :   string or  list of strings
                        one or more names where events are stored
        populations :   string or list of strings
                        one or more names where the populations corresponding to the
                        events are stored. If one population column is provided, it is
                        used for all event columns. If more than one population column
                        is provided but there is not a population for every event
                        column, an exception will be raised.
        w           :   pysal weights object
                        a weights object aligned with the dataframe. If not provided, this
                        is searched for in the dataframe's metadata
        inplace     :   bool
                        a boolean denoting whether to operate on the dataframe inplace or to
                        return a series contaning the results of the computation. If
                        operating inplace, the derived columns will be named
                        'column_moran_rate'
        pvalue      :   string
                        a string denoting which pvalue should be returned. Refer to the
                        the Moran_Rate statistic's documentation for available p-values
        outvals     :   list of strings
                        list of arbitrary attributes to return as columns from the
                        Moran_Rate statistic
        **stat_kws  :   keyword arguments
                        options to pass to the underlying statistic. For this, see the
                        documentation for the Moran_Rate statistic.

        Returns
        --------
        If inplace, None, and operation is conducted on dataframe in memory. Otherwise,
        returns a copy of the dataframe with the relevant columns attached.

        See Also
        ---------
        For further documentation, refer to the Moran_Rate class in pysal.esda
        """
        if not inplace:
            new = df.copy()
            cls.by_col(new, events, populations, w=w, inplace=True,
                              pvalue=pvalue, outvals=outvals, swapname=swapname,
                              **stat_kws)
            return new
        if isinstance(events, str):
            events = [events]
        if isinstance(populations, str):
            populations = [populations]
        if len(populations) < len(events):
            populations = populations * len(events)
        if len(events) != len(populations):
            raise ValueError('There is not a one-to-one matching between events and '
                              'populations!\nEvents: {}\n\nPopulations:'
                              ' {}'.format(events, populations))
        adjusted = stat_kws.pop('adjusted', True)

        if isinstance(adjusted, bool):
            adjusted = [adjusted] * len(events)
        if swapname is '':
            swapname = cls.__name__.lower()

        rates = [assuncao_rate(df[e], df[pop]) if adj
                 else df[e].astype(float) / df[pop]
                 for e,pop,adj in zip(events, populations, adjusted)]
        names = ['-'.join((e,p)) for e,p in zip(events, populations)]
        out_df = df.copy()
        rate_df = out_df.from_items(list(zip(names, rates))) #trick to avoid importing pandas
        stat_df = _univariate_handler(rate_df, names, w=w, inplace=False,
                                      pvalue = pvalue, outvals = outvals,
                                      swapname=swapname,
                                      stat=Moran, #how would this get done w/super?
                                      **stat_kws)
        for col in stat_df.columns:
            df[col] = stat_df[col]

class Moran_Local(object):
    """Local Moran Statistics


    Parameters
    ----------
    y : array
        (n,1), attribute array
    w : W
        weight instance assumed to be aligned with y
    transformation : {'R', 'B', 'D', 'U', 'V'}
                     weights transformation,  default is row-standardized "r".
                     Other options include
                     "B": binary,
                     "D": doubly-standardized,
                     "U": untransformed (general weights),
                     "V": variance-stabilizing.
    permutations   : int
                     number of random permutations for calculation of pseudo
                     p_values
    geoda_quads    : boolean
                     (default=False)
                     If True use GeoDa scheme: HH=1, LL=2, LH=3, HL=4
                     If False use PySAL Scheme: HH=1, LH=2, LL=3, HL=4

    Attributes
    ----------

    y            : array
                   original variable
    w            : W
                   original w object
    permutations : int
                   number of random permutations for calculation of pseudo
                   p_values
    Is           : array
                   local Moran's I values
    q            : array
                   (if permutations>0)
                   values indicate quandrant location 1 HH,  2 LH,  3 LL,  4 HL
    sim          : array (permutations by n)
                   (if permutations>0)
                   I values for permuted samples
    p_sim        : array
                   (if permutations>0)
                   p-values based on permutations (one-sided)
                   null: spatial randomness
                   alternative: the observed Ii is further away or extreme
                   from the median of simulated values. It is either extremelyi
                   high or extremely low in the distribution of simulated Is.
    EI_sim       : array
                   (if permutations>0)
                   average values of local Is from permutations
    VI_sim       : array
                   (if permutations>0)
                   variance of Is from permutations
    seI_sim      : array
                   (if permutations>0)
                   standard deviations of Is under permutations.
    z_sim        : arrray
                   (if permutations>0)
                   standardized Is based on permutations
    p_z_sim      : array
                   (if permutations>0)
                   p-values based on standard normal approximation from
                   permutations (one-sided)
                   for two-sided tests, these values should be multiplied by 2

    Examples
    --------
    >>> import libpysal.api as lps
    >>> import numpy as np
    >>> np.random.seed(10)
    >>> w = lps.open(lps.get_path("desmith.gal")).read()
    >>> f = lps.open(lps.get_path("desmith.txt"))
    >>> y = np.array(f.by_col['z'])
    >>> from esda.moran import Moran_Local
    >>> lm = Moran_Local(y, w, transformation = "r", permutations = 99)
    >>> lm.q
    array([4, 4, 4, 2, 3, 3, 1, 4, 3, 3])
    >>> lm.p_z_sim[0]
    0.24669152541631179
    >>> lm = Moran_Local(y, w, transformation = "r", permutations = 99, \
                            geoda_quads=True)
    >>> lm.q
    array([4, 4, 4, 3, 2, 2, 1, 4, 2, 2])

    Note random components result is slightly different values across
    architectures so the results have been removed from doctests and will be
    moved into unittests that are conditional on architectures
    """
    def __init__(self, y, w, transformation="r", permutations=PERMUTATIONS,
                 geoda_quads=False):
        y = np.asarray(y).flatten()
        self.y = y
        n = len(y)
        self.n = n
        self.n_1 = n - 1
        z = y - y.mean()
        # setting for floating point noise
        orig_settings = np.seterr()
        np.seterr(all="ignore")
        sy = y.std()
        z /= sy
        np.seterr(**orig_settings)
        self.z = z
        w.transform = transformation
        self.w = w
        self.permutations = permutations
        self.den = (z * z).sum()
        self.Is = self.calc(self.w, self.z)
        self.geoda_quads = geoda_quads
        quads = [1, 2, 3, 4]
        if geoda_quads:
            quads = [1, 3, 2, 4]
        self.quads = quads
        self.__quads()
        if permutations:
            self.__crand()
            sim = np.transpose(self.rlisas)
            above = sim >= self.Is
            larger = above.sum(0)
            low_extreme = (self.permutations - larger) < larger
            larger[low_extreme] = self.permutations - larger[low_extreme]
            self.p_sim = (larger + 1.0) / (permutations + 1.0)
            self.sim = sim
            self.EI_sim = sim.mean(axis=0)
            self.seI_sim = sim.std(axis=0)
            self.VI_sim = self.seI_sim * self.seI_sim
            self.z_sim = (self.Is - self.EI_sim) / self.seI_sim
            self.p_z_sim = 1 - stats.norm.cdf(np.abs(self.z_sim))

    def calc(self, w, z):
        zl = slag(w, z)
        return self.n_1 * self.z * zl / self.den

    def __crand(self):
        """
        conditional randomization

        for observation i with ni neighbors,  the candidate set cannot include
        i (we don't want i being a neighbor of i). we have to sample without
        replacement from a set of ids that doesn't include i. numpy doesn't
        directly support sampling wo replacement and it is expensive to
        implement this. instead we omit i from the original ids,  permute the
        ids and take the first ni elements of the permuted ids as the
        neighbors to i in each randomization.

        """
        z = self.z
        lisas = np.zeros((self.n, self.permutations))
        n_1 = self.n - 1
        prange = list(range(self.permutations))
        k = self.w.max_neighbors + 1
        nn = self.n - 1
        rids = np.array([np.random.permutation(nn)[0:k] for i in prange])
        ids = np.arange(self.w.n)
        ido = self.w.id_order
        w = [self.w.weights[ido[i]] for i in ids]
        wc = [self.w.cardinalities[ido[i]] for i in ids]

        for i in range(self.w.n):
            idsi = ids[ids != i]
            np.random.shuffle(idsi)
            tmp = z[idsi[rids[:, 0:wc[i]]]]
            lisas[i] = z[i] * (w[i] * tmp).sum(1)
        self.rlisas = (n_1 / self.den) * lisas

    def __quads(self):
        zl = slag(self.w, self.z)
        zp = self.z > 0
        lp = zl > 0
        pp = zp * lp
        np = (1 - zp) * lp
        nn = (1 - zp) * (1 - lp)
        pn = zp * (1 - lp)
        self.q = self.quads[0] * pp + self.quads[1] * np + self.quads[2] * nn \
            + self.quads[3] * pn

    @property
    def _statistic(self):
        """More consistent hidden attribute to access ESDA statistics"""
        return self.Is

    @classmethod
    def by_col(cls, df, cols, w=None, inplace=False, pvalue='sim', outvals=None, **stat_kws):
        """
        Function to compute a Moran_Local statistic on a dataframe

        Arguments
        ---------
        df          :   pandas.DataFrame
                        a pandas dataframe with a geometry column
        cols        :   string or list of string
                        name or list of names of columns to use to compute the statistic
        w           :   pysal weights object
                        a weights object aligned with the dataframe. If not provided, this
                        is searched for in the dataframe's metadata
        inplace     :   bool
                        a boolean denoting whether to operate on the dataframe inplace or to
                        return a series contaning the results of the computation. If
                        operating inplace, the derived columns will be named
                        'column_moran_local'
        pvalue      :   string
                        a string denoting which pvalue should be returned. Refer to the
                        the Moran_Local statistic's documentation for available p-values
        outvals     :   list of strings
                        list of arbitrary attributes to return as columns from the
                        Moran_Local statistic
        **stat_kws  :   keyword arguments
                        options to pass to the underlying statistic. For this, see the
                        documentation for the Moran_Local statistic.

        Returns
        --------
        If inplace, None, and operation is conducted on dataframe in memory. Otherwise,
        returns a copy of the dataframe with the relevant columns attached.

        See Also
        ---------
        For further documentation, refer to the Moran_Local class in pysal.esda
        """
        return _univariate_handler(df, cols, w=w, inplace=inplace, pvalue=pvalue,
                                   outvals=outvals, stat=cls,
                                   swapname=cls.__name__.lower(), **stat_kws)
    
    def plot(self, gdf, attribute, p=0.05,
             region_column=None, mask=None,
             mask_color='#636363', quadrant=None,
             legend=True, scheme='Quantiles',
             cmap='YlGnBu', figsize=(15,4)):
        """Produce three-plot visualization of Moran Scatteprlot,
        LISA cluster and Choropleth, with Local Moran
        region and quadrant masking

        Parameters
        ----------
        gdf : geopandas dataframe
            The Dataframe containing information to plot the two maps.
        attribute : str
            Column name of attribute which should be depicted in Choropleth map.
        p : float, optional
            The p-value threshold for significance. Points and polygons will
            be colored by significance. Default = 0.05.
        region_column: string, optional
            Column name containing mask region of interest. Default = None
        mask: str, optional
            Identifier or name of the region to highlight. Default = None
        mask_color: str, optional
            Color of mask. Default = '#636363'
        quadrant : int, optional
            Quadrant 1-4 in scatterplot masking values in LISA cluster and
            Choropleth maps. Default = None
        figsize: tuple, optional
            W, h of figure. Default = (15,4)
        legend: boolean, optional
            If True, legend for maps will be depicted. Default = True
        scheme: str, optional
            Name of PySAL classifier to be used. Default = 'Quantiles'
        cmap: str, optional
            Name of matplotlib colormap used for plotting the Choropleth.
            Default = 'YlGnBU'

        Returns
        -------
        fig : matplotlip Figure instance
            Figure of LISA cluster map
        ax : matplotlib Axes instance
            Axes in which the figure is plotted
            
        Examples
        --------
        """
        try:
            import splot.esda
        except ImportError as e:
            warnings.warn('This method will be available as soon as splot is released in September 2018',
                          UserWarning)
            raise e

        fig, axs = splot.esda.plot_local_autocorrelation(self, gdf=gdf,
                                                        attribute=attribute,
                                                        p=p,
                                                        region_column=region_column,
                                                        mask=mask,
                                                        mask_color=mask_color,
                                                        quadrant=quadrant,
                                                        legend=legend,
                                                        scheme=scheme,
                                                        cmap=cmap,
                                                        figsize=figsize)
        return fig, axs
    
    def scatterplot(self, p=0.05, **kwargs):
        """Plot Local Moran Scatterplot

        Parameters
        ----------
        p : float, optional
            The p-value threshold for significance. Points will
            be colored by LISA and significance. Default=0.05
        **kwargs : keyword arguments, optional
            Keywords used for creating and designing the plot.

        Returns
        -------
        fig : matplotlip Figure instance
            Figure of LISA cluster map
        ax : matplotlib Axes instance
            Axes in which the figure is plotted
            
        Examples
        --------
        """
        try:
            import splot.esda
        except ImportError as e:
            warnings.warn('This method will be available as soon as splot is released in September 2018',
                          UserWarning)
            raise e

        fig, ax = splot.esda.moran_loc_scatterplot(self, p=p, **kwargs)
        return fig, ax


    def LISA_map(self, gdf, p=0.05,
                 legend=True, **kwargs):
        """Plot LISA cluster map

        Parameters
        ----------
        gdf : geopandas dataframe instance
            The Dataframe containing information to plot. Note that `gdf` will be
            modified, so calling functions should use a copy of the user
            provided `gdf`. (either using gdf.assign() or gdf.copy())
        p : float, optional
            The p-value threshold for significance. Points will
            be colored by significance. Default =0.05
        legend : boolean, optional
            If True, legend for maps will be depicted. Default = True
        **kwargs : keyword arguments, optional
            Keywords used for creating and designing the plot.

        Returns
        -------
        fig : matplotlip Figure instance
            Figure of LISA cluster map
        ax : matplotlib Axes instance
            Axes in which the figure is plotted
            
        Examples
        --------
        """
        try:
            import splot.esda
        except ImportError as e:
            warnings.warn('This method will be available as soon as splot is released in September 2018',
                          UserWarning)
            raise e

        fig, ax = splot.esda.lisa_cluster(self, p=p, **kwargs)
        return fig, ax


class Moran_Local_BV(object):
    """Bivariate Local Moran Statistics


    Parameters
    ----------
    x : array
        x-axis variable
    y : array
        (n,1), wy will be on y axis
    w : W
        weight instance assumed to be aligned with y
    transformation : {'R', 'B', 'D', 'U', 'V'}
                     weights transformation,  default is row-standardized "r".
                     Other options include
                     "B": binary,
                     "D": doubly-standardized,
                     "U": untransformed (general weights),
                     "V": variance-stabilizing.
    permutations   : int
                     number of random permutations for calculation of pseudo
                     p_values
    geoda_quads    : boolean
                     (default=False)
                     If True use GeoDa scheme: HH=1, LL=2, LH=3, HL=4
                     If False use PySAL Scheme: HH=1, LH=2, LL=3, HL=4

    Attributes
    ----------

    zx           : array
                   original x variable standardized by mean and std
    zy           : array
                   original y variable standardized by mean and std
    w            : W
                   original w object
    permutations : int
                   number of random permutations for calculation of pseudo
                   p_values
    Is           : float
                   value of Moran's I
    q            : array
                   (if permutations>0)
                   values indicate quandrant location 1 HH,  2 LH,  3 LL,  4 HL
    sim          : array
                   (if permutations>0)
                   vector of I values for permuted samples
    p_sim        : array
                   (if permutations>0)
                   p-value based on permutations (one-sided)
                   null: spatial randomness
                   alternative: the observed Ii is further away or extreme
                   from the median of simulated values. It is either extremelyi
                   high or extremely low in the distribution of simulated Is.
    EI_sim       : array
                   (if permutations>0)
                   average values of local Is from permutations
    VI_sim       : array
                   (if permutations>0)
                   variance of Is from permutations
    seI_sim      : array
                   (if permutations>0)
                   standard deviations of Is under permutations.
    z_sim        : arrray
                   (if permutations>0)
                   standardized Is based on permutations
    p_z_sim      : array
                   (if permutations>0)
                   p-values based on standard normal approximation from
                   permutations (one-sided)
                   for two-sided tests, these values should be multiplied by 2


    Examples
    --------
    >>> import libpysal.api as lps
    >>> import numpy as np
    >>> np.random.seed(10)
    >>> w = lps.open(lps.get_path("sids2.gal")).read()
    >>> f = lps.open(lps.get_path("sids2.dbf"))
    >>> x = np.array(f.by_col['SIDR79'])
    >>> y = np.array(f.by_col['SIDR74'])
    >>> from esda.moran import Moran_Local_BV
    >>> lm =Moran_Local_BV(x, y, w, transformation = "r", \
                               permutations = 99)
    >>> lm.q[:10]
    array([3, 4, 3, 4, 2, 1, 4, 4, 2, 4])
    >>> lm = Moran_Local_BV(x, y, w, transformation = "r", \
                               permutations = 99, geoda_quads=True)
    >>> lm.q[:10]
    array([2, 4, 2, 4, 3, 1, 4, 4, 3, 4])

    Note random components result is slightly different values across
    architectures so the results have been removed from doctests and will be
    moved into unittests that are conditional on architectures
    """
    def __init__(self, x, y, w, transformation="r", permutations=PERMUTATIONS,
                 geoda_quads=False):
        x = np.asarray(x).flatten()
        y = np.asarray(y).flatten()
        self.y = y
        self.x =x
        n = len(y)
        self.n = n
        self.n_1 = n - 1
        zx = x - x.mean()
        zy = y - y.mean()
        # setting for floating point noise
        orig_settings = np.seterr()
        np.seterr(all="ignore")
        sx = x.std()
        zx /= sx
        sy = y.std()
        zy /= sy
        np.seterr(**orig_settings)
        self.zx = zx
        self.zy = zy
        w.transform = transformation
        self.w = w
        self.permutations = permutations
        self.den = (zx * zx).sum()
        self.Is = self.calc(self.w, self.zx, self.zy)
        self.geoda_quads = geoda_quads
        quads = [1, 2, 3, 4]
        if geoda_quads:
            quads = [1, 3, 2, 4]
        self.quads = quads
        self.__quads()
        if permutations:
            self.__crand()
            sim = np.transpose(self.rlisas)
            above = sim >= self.Is
            larger = above.sum(0)
            low_extreme = (self.permutations - larger) < larger
            larger[low_extreme] = self.permutations - larger[low_extreme]
            self.p_sim = (larger + 1.0) / (permutations + 1.0)
            self.sim = sim
            self.EI_sim = sim.mean(axis=0)
            self.seI_sim = sim.std(axis=0)
            self.VI_sim = self.seI_sim * self.seI_sim
            self.z_sim = (self.Is - self.EI_sim) / self.seI_sim
            self.p_z_sim = 1 - stats.norm.cdf(np.abs(self.z_sim))

    def calc(self, w, zx, zy):
        zly = slag(w, zy)
        return self.n_1 * self.zx * zly / self.den

    def __crand(self):
        """
        conditional randomization

        for observation i with ni neighbors,  the candidate set cannot include
        i (we don't want i being a neighbor of i). we have to sample without
        replacement from a set of ids that doesn't include i. numpy doesn't
        directly support sampling wo replacement and it is expensive to
        implement this. instead we omit i from the original ids,  permute the
        ids and take the first ni elements of the permuted ids as the
        neighbors to i in each randomization.

        """
        lisas = np.zeros((self.n, self.permutations))
        n_1 = self.n - 1
        prange = list(range(self.permutations))
        k = self.w.max_neighbors + 1
        nn = self.n - 1
        rids = np.array([np.random.permutation(nn)[0:k] for i in prange])
        ids = np.arange(self.w.n)
        ido = self.w.id_order
        w = [self.w.weights[ido[i]] for i in ids]
        wc = [self.w.cardinalities[ido[i]] for i in ids]

        zx = self.zx
        zy = self.zy
        for i in range(self.w.n):
            idsi = ids[ids != i]
            np.random.shuffle(idsi)
            tmp = zy[idsi[rids[:, 0:wc[i]]]]
            lisas[i] = zx[i] * (w[i] * tmp).sum(1)
        self.rlisas = (n_1 / self.den) * lisas

    def __quads(self):
        zl = slag(self.w, self.zy)
        zp = self.zx > 0
        lp = zl > 0
        pp = zp * lp
        np = (1 - zp) * lp
        nn = (1 - zp) * (1 - lp)
        pn = zp * (1 - lp)
        self.q = self.quads[0] * pp + self.quads[1] * np + self.quads[2] * nn \
            + self.quads[3] * pn

    @property
    def _statistic(self):
        """More consistent hidden attribute to access ESDA statistics"""
        return self.Is

    @classmethod
    def by_col(cls, df, x, y=None, w=None, inplace=False, pvalue='sim', outvals=None, **stat_kws):
        """
        Function to compute a Moran_Local_BV statistic on a dataframe

        Arguments
        ---------
        df          :   pandas.DataFrame
                        a pandas dataframe with a geometry column
        X           :   list of strings
                        column name or list of column names to use as X values to compute
                        the bivariate statistic. If no Y is provided, pairwise comparisons
                        among these variates are used instead.
        Y           :   list of strings
                        column name or list of column names to use as Y values to compute
                        the bivariate statistic. if no Y is provided, pariwise comparisons
                        among the X variates are used instead.
        w           :   pysal weights object
                        a weights object aligned with the dataframe. If not provided, this
                        is searched for in the dataframe's metadata
        inplace     :   bool
                        a boolean denoting whether to operate on the dataframe inplace or to
                        return a series contaning the results of the computation. If
                        operating inplace, the derived columns will be named
                        'column_moran_local_bv'
        pvalue      :   string
                        a string denoting which pvalue should be returned. Refer to the
                        the Moran_Local_BV statistic's documentation for available p-values
        outvals     :   list of strings
                        list of arbitrary attributes to return as columns from the
                        Moran_Local_BV statistic
        **stat_kws  :   keyword arguments
                        options to pass to the underlying statistic. For this, see the
                        documentation for the Moran_Local_BV statistic.


        Returns
        --------
        If inplace, None, and operation is conducted on dataframe in memory. Otherwise,
        returns a copy of the dataframe with the relevant columns attached.

        See Also
        ---------
        For further documentation, refer to the Moran_Local_BV class in pysal.esda
        """
        return _bivariate_handler(df, x, y=y, w=w, inplace=inplace,
                                  pvalue = pvalue, outvals = outvals,
                                  swapname=cls.__name__.lower(), stat=cls,**stat_kws)

class Moran_Local_Rate(Moran_Local):
    """
    Adjusted Local Moran Statistics for Rate Variables [Assuncao1999]_

    Parameters
    ----------
    e : array
        (n,1), an event variable across n spatial units
    b : array
        (n,1), a population-at-risk variable across n spatial units
    w : W
        weight instance assumed to be aligned with y
    adjusted : boolean
              whether or not local Moran statistics need to be adjusted for
              rate variable
    transformation : {'R', 'B', 'D', 'U', 'V'}
                     weights transformation,  default is row-standardized "r".
                     Other options include
                     "B": binary,
                     "D": doubly-standardized,
                     "U": untransformed (general weights),
                     "V": variance-stabilizing.
    permutations   : int
                     number of random permutations for calculation of pseudo
                     p_values
    geoda_quads    : boolean
                     (default=False)
                     If True use GeoDa scheme: HH=1, LL=2, LH=3, HL=4
                     If False use PySAL Scheme: HH=1, LH=2, LL=3, HL=4
    Attributes
    ----------
    y            : array
                   rate variables computed from parameters e and b
                   if adjusted is True, y is standardized rates
                   otherwise, y is raw rates
    w            : W
                   original w object
    permutations : int
                   number of random permutations for calculation of pseudo
                   p_values
    I            : float
                   value of Moran's I
    q            : array
                   (if permutations>0)
                   values indicate quandrant location 1 HH,  2 LH,  3 LL,  4 HL
    sim          : array
                   (if permutations>0)
                   vector of I values for permuted samples
    p_sim        : array
                   (if permutations>0)
                   p-value based on permutations (one-sided)
                   null: spatial randomness
                   alternative: the observed Ii is further away or extreme
                   from the median of simulated Iis. It is either extremely
                   high or extremely low in the distribution of simulated Is
    EI_sim       : float
                   (if permutations>0)
                   average value of I from permutations
    VI_sim       : float
                   (if permutations>0)
                   variance of I from permutations
    seI_sim      : float
                   (if permutations>0)
                   standard deviation of I under permutations.
    z_sim        : float
                   (if permutations>0)
                   standardized I based on permutations
    p_z_sim      : float
                   (if permutations>0)
                   p-value based on standard normal approximation from
                   permutations (one-sided)
                   for two-sided tests, these values should be multiplied by 2

    Examples
    --------
    >>> import libpysal.api as lps
    >>> import numpy as np
    >>> np.random.seed(10)
    >>> w = lps.open(lps.get_path("sids2.gal")).read()
    >>> f = lps.open(lps.get_path("sids2.dbf"))
    >>> e = np.array(f.by_col('SID79'))
    >>> b = np.array(f.by_col('BIR79'))
    >>> from esda.moran import Moran_Local_Rate
    >>> lm = Moran_Local_Rate(e, b, w, transformation = "r", permutations = 99)
    >>> lm.q[:10]
    array([2, 4, 3, 1, 2, 1, 1, 4, 2, 4])
    >>> lm = Moran_Local_Rate(e, b, w,  transformation = "r",  permutations = 99,  geoda_quads=True)
    >>> lm.q[:10]
    array([3, 4, 2, 1, 3, 1, 1, 4, 3, 4])

    Note random components result is slightly different values across
    architectures so the results have been removed from doctests and will be
    moved into unittests that are conditional on architectures
    """

    def __init__(self, e, b, w, adjusted=True, transformation="r",
                 permutations=PERMUTATIONS, geoda_quads=False):
        e = np.asarray(e).flatten()
        b = np.asarray(b).flatten()
        if adjusted:
            y = assuncao_rate(e, b)
        else:
            y = e * 1.0 / b
        Moran_Local.__init__(self, y, w,
                             transformation=transformation,
                             permutations=permutations,
                             geoda_quads=geoda_quads)

    @classmethod
    def by_col(cls, df, events, populations, w=None, inplace=False,
               pvalue='sim', outvals=None, swapname='',  **stat_kws):
        """
        Function to compute a Moran_Local_Rate statistic on a dataframe

        Arguments
        ---------
        df          :   pandas.DataFrame
                        a pandas dataframe with a geometry column
        events      :   string or  list of strings
                        one or more names where events are stored
        populations :   string or list of strings
                        one or more names where the populations corresponding to the
                        events are stored. If one population column is provided, it is
                        used for all event columns. If more than one population column
                        is provided but there is not a population for every event
                        column, an exception will be raised.
        w           :   pysal weights object
                        a weights object aligned with the dataframe. If not provided, this
                        is searched for in the dataframe's metadata
        inplace     :   bool
                        a boolean denoting whether to operate on the dataframe inplace or to
                        return a series contaning the results of the computation. If
                        operating inplace, the derived columns will be named 'column_moran_local_rate'
        pvalue      :   string
                        a string denoting which pvalue should be returned. Refer to the
                        the Moran_Local_Rate statistic's documentation for available p-values
        outvals     :   list of strings
                        list of arbitrary attributes to return as columns from the
                        Moran_Local_Rate statistic
        **stat_kws  :   keyword arguments
                        options to pass to the underlying statistic. For this, see the
                        documentation for the Moran_Local_Rate statistic.

        Returns
        --------
        If inplace, None, and operation is conducted on dataframe in memory. Otherwise,
        returns a copy of the dataframe with the relevant columns attached.

        See Also
        ---------
        For further documentation, refer to the Moran_Local_Rate class in pysal.esda
        """
        if not inplace:
            new = df.copy()
            cls.by_col(new, events, populations, w=w, inplace=True,
                              pvalue=pvalue, outvals=outvals, swapname=swapname,
                              **stat_kws)
            return new
        if isinstance(events, str):
            events = [events]
        if isinstance(populations, str):
            populations = [populations]
        if len(populations) < len(events):
            populations = populations * len(events)
        if len(events) != len(populations):
            raise ValueError('There is not a one-to-one matching between events and '
                              'populations!\nEvents: {}\n\nPopulations:'
                              ' {}'.format(events, populations))
        adjusted = stat_kws.pop('adjusted', True)

        if isinstance(adjusted, bool):
            adjusted = [adjusted] * len(events)
        if swapname is '':
            swapname = cls.__name__.lower()

        rates = [assuncao_rate(df[e], df[pop]) if adj
                 else df[e].astype(float) / df[pop]
                 for e,pop,adj in zip(events, populations, adjusted)]
        names = ['-'.join((e,p)) for e,p in zip(events, populations)]
        out_df = df.copy()
        rate_df = out_df.from_items(list(zip(names, rates))) #trick to avoid importing pandas
        _univariate_handler(rate_df, names, w=w, inplace=True,
                                      pvalue = pvalue, outvals = outvals,
                                      swapname=swapname,
                                      stat=Moran_Local, #how would this get done w/super?
                                      **stat_kws)
        for col in rate_df.columns:
            df[col] = rate_df[col]
