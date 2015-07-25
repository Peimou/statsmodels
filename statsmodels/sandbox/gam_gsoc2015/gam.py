import numpy as np
import scipy as sp
from scipy.linalg import block_diag
from statsmodels.discrete.discrete_model import Logit
from statsmodels.genmod.generalized_linear_model import GLM, GLMResults
from scipy.linalg import pinv
from scipy.stats import chi2

## this class will be later removed and taken from another push
class PenalizedMixin(object):
    """Mixin class for Maximum Penalized Likelihood
    TODO: missing **kwds or explicit keywords
    TODO: do we really need `pen_weight` keyword in likelihood methods?
    """

    def __init__(self, *args, **kwds):
        super(PenalizedMixin, self).__init__(*args, **kwds)

        penal = kwds.pop('penal', None)
        # I keep the following instead of adding default in pop for future changes
        if penal is None:
            # TODO: switch to unpenalized by default
            self.penal = SCADSmoothed(0.1, c0=0.0001)
        else:
            self.penal = penal

        # TODO: define pen_weight as average pen_weight? i.e. per observation
        # I would have prefered len(self.endog) * kwds.get('pen_weight', 1)
        # or use pen_weight_factor in signature
        self.pen_weight =  kwds.get('pen_weight', len(self.endog))

        self._init_keys.extend(['penal', 'pen_weight'])

    def loglike(self, params, pen_weight=None):
        if pen_weight is None:
            pen_weight = self.pen_weight

        llf = super(PenalizedMixin, self).loglike(params)
        if pen_weight != 0:
            llf -= pen_weight * self.penal.func(params)

        return llf

    def loglikeobs(self, params, pen_weight=None):
        if pen_weight is None:
            pen_weight = self.pen_weight

        llf = super(PenalizedMixin, self).loglikeobs(params)
        nobs_llf = float(llf.shape[0])

        if pen_weight != 0:
            llf -= pen_weight / nobs_llf * self.penal.func(params)

        return llf

    def score(self, params, pen_weight=None):
        if pen_weight is None:
            pen_weight = self.pen_weight

        sc = super(PenalizedMixin, self).score(params)
        if pen_weight != 0:
            sc -= pen_weight * self.penal.grad(params)

        return sc

    def scoreobs(self, params, pen_weight=None):
        if pen_weight is None:
            pen_weight = self.pen_weight

        sc = super(PenalizedMixin, self).scoreobs(params)
        nobs_sc = float(sc.shape[0])
        if pen_weight != 0:
            sc -= pen_weight / nobs_sc  * self.penal.grad(params)

        return sc

    def hessian_(self, params, pen_weight=None):
        if pen_weight is None:
            pen_weight = self.pen_weight
            loglike = self.loglike
        else:
            loglike = lambda p: self.loglike(p, pen_weight=pen_weight)

        from statsmodels.tools.numdiff import approx_hess
        return approx_hess(params, loglike)

    def hessian(self, params, pen_weight=None):
        if pen_weight is None:
            pen_weight = self.pen_weight

        hess = super(PenalizedMixin, self).hessian(params)
        if pen_weight != 0:
            h = self.penal.deriv2(params)
            if h.ndim == 1:
                hess -= np.diag(pen_weight * h)
            else:
                hess -= pen_weight * h

        return hess

    def fit(self, method=None, trim=None, **kwds):
        # If method is None, then we choose a default method ourselves

        # TODO: temporary hack, need extra fit kwds
        # we need to rule out fit methods in a model that will not work with
        # penalization
        if hasattr(self, 'family'):  # assume this identifies GLM
            kwds.update({'max_start_irls' : 0})

        # currently we use `bfgs` by default
        if method is None:
            method = 'bfgs'

        if trim is None:
            trim = False  # see below infinite recursion in `fit_constrained

        res = super(PenalizedMixin, self).fit(method=method, **kwds)

        if trim is False:
            # note boolean check for "is False" not evaluates to False
            return res
        else:
            # TODO: make it penal function dependent
            # temporary standin, only works for Poisson and GLM,
            # and is computationally inefficient
            drop_index = np.nonzero(np.abs(res.params) < 1e-4) [0]
            keep_index = np.nonzero(np.abs(res.params) > 1e-4) [0]
            rmat = np.eye(len(res.params))[drop_index]

            # calling fit_constrained raise
            # "RuntimeError: maximum recursion depth exceeded in __instancecheck__"
            # fit_constrained is calling fit, recursive endless loop
            if drop_index.any():
                # todo : trim kwyword doesn't work, why not?
                #res_aux = self.fit_constrained(rmat, trim=False)
                res_aux = self._fit_zeros(keep_index, **kwds)
                return res_aux
            else:
                return res


## this class will be later removed and taken from another push
class Penalty(object):
    """
    A class for representing a scalar-value penalty.
    Parameters
    wts : array-like
        A vector of weights that determines the weight of the penalty
        for each parameter.
    Notes
    -----
    The class has a member called `alpha` that scales the weights.
    """

    def __init__(self, wts):
        self.wts = wts
        self.alpha = 1.

    def func(self, params):
        """
        A penalty function on a vector of parameters.
        Parameters
        ----------
        params : array-like
            A vector of parameters.
        Returns
        -------
        A scalar penaty value; greater values imply greater
        penalization.
        """
        raise NotImplementedError

    def grad(self, params):
        """
        The gradient of a penalty function.
        Parameters
        ----------
        params : array-like
            A vector of parameters
        Returns
        -------
        The gradient of the penalty with respect to each element in
        `params`.
        """
        raise NotImplementedError


class GamPenalty(Penalty):
    __doc__ = """
    Penalty for Generalized Additive Models class

    Parameters
    -----------
    alpha : float
        the penalty term

    wts: TODO: I do not know!

    cov_der2: the covariance matrix of the second derivative of the basis matrix

    der2: The second derivative of the basis function

    Attributes
    -----------
    alpha : float
        the penalty term

    wts: TODO: I do not know!

    cov_der2: the covariance matrix of the second derivative of the basis matrix

    der2: The second derivative of the basis function

    n_samples: The number of samples used during the estimation



    """

    def __init__(self, wts=1, alpha=1, cov_der2=None, der2=None):

        self.wts = wts #should we keep wts????
        self.alpha = alpha
        self.cov_der2 = cov_der2
        self.der2 = der2
        self.n_samples = der2.shape[0]

    def func(self, params):
        '''
        1) params are the coefficients in the regression model
        2) der2  is the second derivative of the splines basis
        '''

        # The second derivative of the estimated regression function
        f = np.dot(self.der2, params)

        return self.alpha * np.sum(f**2) / self.n_samples

    def grad(self, params):
        '''
        1) params are the coefficients in the regression model
        2) der2  is the second derivative of the splines basis
        3) cov_der2 is obtained as np.dot(der2.T, der2)
        '''

        return 2 * self.alpha * np.dot(self.cov_der2, params) / self.n_samples

    def deriv2(self, params):

        return 2 * self.alpha * self.cov_der2 / self.n_samples




class MultivariateGamPenalty(Penalty):
    __doc__ = """
    GAM penalty for multivariate regression

    Parameters
    -----------
    cov_der2: list of matrices
     is a list of squared matrix of shape (size_base, size_base)

    der2: list of matrices
     is a list of matrix of shape (n_samples, size_base)

    alpha: array-like
     list of doubles. Each one representing the penalty
          for each function

    wts: array-like
     is a list of doubles of the same length of alpha

    """

    def __init__(self, wts=None, alphas=None, cov_der2=None, der2=None):

        if len(cov_der2) != len(der2) or len(alphas) != len(der2):
            raise ValueError('all the input values should be list of the same length')

        # the total number of columns in der2 i.e. the len of the params vector
        self.k_columns = np.sum(d2.shape[1] for d2 in der2)

        # the number of variables in the GAM model
        self.n_variables = len(cov_der2)

        # if wts and alpha are not a list then each function has the same penalty
        # TODO: Review this
        self.alphas = alphas
        self.wts = wts

        n_samples = der2[0].shape[0]
        self.mask = [np.array([False]*self.k_columns)
                     for _ in range(self.n_variables)]
        param_count = 0
        for i, d2 in enumerate(der2):
            n, dim_base = d2.shape
            # check that all the basis have the same number of samples
            assert(n_samples == n)
            # the mask[i] contains a vector of length k_columns. The index
            # corresponding to the i-th input variable are set to True.
            self.mask[i][param_count: param_count + dim_base] = True
            param_count += dim_base

        self.gp = []
        for i in range(self.n_variables):
            gp = GamPenalty(wts=self.wts[i], alpha=self.alphas[i],
                            cov_der2=cov_der2[i], der2=der2[i])
            self.gp.append(gp)

        return

    def func(self, params):
        cost = 0
        for i in range(self.n_variables):
            params_i = params[self.mask[i]]
            cost += self.gp[i].func(params_i)

        return cost

    def grad(self, params):
        grad = []
        for i in range(self.n_variables):
            params_i = params[self.mask[i]]
            grad.append(self.gp[i].grad(params_i))

        return np.concatenate(grad)

    def deriv2(self, params):
        deriv2 = np.empty(shape=(0,0))
        for i in range(self.n_variables):
            params_i = params[self.mask[i]]
            deriv2 = block_diag(deriv2, self.gp[i].deriv2(params_i))

        return deriv2


class LogitGam(PenalizedMixin, Logit):
    pass


class GLMGAMResults(GLMResults):

    def plot_predict(self, x_values=None, smooth_basis=None):
        """just to try a method in overridden Results class
        """
        import matplotlib.pyplot as plt
        # TODO: This function will be available when we will have the self.model.x variable
        # if x_values is None:
        #     plt.plot(self.model.x, self.model.endog, '.')
        #     plt.plot(self.model.x, self.predict())
        # else:
        plt.plot(x_values, self.predict(smooth_basis))

    def significance_test(self, basis=None):
        v = basis.dot(self.normalized_cov_params).dot(basis.T)
        p_inv_v, rank = pinv(v, return_rank=True) # TODO: According to the paper the partial inverse should be done with rank r accurately chosen
        f = self.predict(basis)
        tr = f.T.dot(p_inv_v).dot(f)
        # TODO: the value tr should be used to perform a wald test. This can be probably done by the ConstrastResult class but it is not clear how.

        print('rank=', rank) # TODO: Rank is often not the expected value. Run for example the draft code
        p_val = 1 - chi2.cdf(tr, df=rank)# TODO: basis_size should probably be replaced by rank

        return tr, p_val, rank


class GLMGam(PenalizedMixin, GLM):

    _results_class = GLMGAMResults
