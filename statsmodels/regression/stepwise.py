# -*- coding: utf-8 -*-
"""Sequential using QR and Stepwise Regression using Sweep algorithm

Created on Fri Jun 22 19:15:17 2012

Author: Josef Perktold
"""

import numpy as np
import statsmodels.tools.eval_measures as evm

class SequentialOLSQR(object):

    def __init__(self, endog, exog, start_idx=0):
        self.endog = endog
        self.exog = exog
        self.start_idx = start_idx
        self.nobs, self.k_vars = exog.shape

        self.xy = np.column_stack((exog, endog))
        self.q, self.r = np.linalg.qr(self.xy)
        self.ssr = self.r[-1,-1]**2
        self.ss_contrib = ss_contrib = self.r[:-1,-1]**2
        self.ess_uncentered = ss_contrib.sum()
        self.uncentered_tss = np.dot(endog.T, endog)
        self.ess_all = ss_contrib.cumsum()
        assert self.uncentered_tss, self.ess_all[-1] + self.ssr
        self.ssr_all = self.uncentered_tss - ss_contrib.cumsum()
        self.dfmodelwc = np.arange(1, self.k_vars+1)

    def r_inv(self):
        return np.linalg.inv(self.r[:-1, :-1])

    def normalized_covparams(self):
        return np.dot(self.r_inv.T, self.r_inv)


    def llf_all(self):
        return loglike_ssr(self.ssr_all, self.nobs)

#explicit versions not used or finished with refactoring - names
#    def aic_all(self):
#        aic = [evm.aic_sigma(ssrs[i], nobs, self.dfmodelwc[i])
#                          for i in range(k_vars)]
#        return np.array(aic)
#
#    def bic_all(self):
#        bic = [evm.aic_sigma(ssrs[i], nobs, self.dfmodelwc[i])
#                          for i in range(k_vars)]
#        return np.array(bic)

    def ic_sigma_all(self, ic='bic'):
        ic_func = getattr(evm, ic + '_sigma')
        ic = ic_func(self.ssr_all, self.nobs, self.dfmodelwc) #is vectorized with arrays
        return np.asarray(ic)

    def ic_all(self, ic='bic'):
        ic_func = getattr(evm, ic)
        ic = ic_func(self.llf_all(), self.nobs, self.dfmodelwc) #is vectorized with arrays
        return np.asarray(ic)

    def min_ic_idx(self, ic='bic'):
        '''index of minimum ic model, contains idx + 1 variables/columns

        '''
        ic = self.ic_all(ic=ic)
        argmin_ic = self.start_idx + np.argmin(ic[self.start_idx:])
        return argmin_ic

def loglike_ssr(ssr, nobs):
    '''
    Get likelihood function value from ssr for OLS model.

    Parameters
    ----------
    params : array-like
        The coefficients with which to estimate the loglikelihood.

    Returns
    -------
    The concentrated likelihood function evaluated at params.
    '''
    nobs2 = nobs/2.
    return -nobs2 * (np.log(2*np.pi) + np.log(ssr / nobs) + 1)

########################  Sweep for Stepwise Regression ###################

def sweep(k, rs):
    k_vars = rs.shape[1] - 1
    #TODO: can we do inplace sweep ?
    rkk = rs[k, k].copy()
    rs_next = rs.copy()
    not_k = np.ones(k_vars+1, bool)
    not_k[k] = False
    #sweep in 4 steps
    rs_next[:,k] /= rkk
    rs_next[k, :] /= -rkk
    #next is same as outer but dot is more explicit
    rs_next[not_k[:,None] * not_k] -= np.dot(rs[not_k, k:k+1], rs[k:k+1, not_k]).ravel() / rkk
    rs_next[k,k] = 1. / rkk

    return rs_next




class StepwiseOLSSweep(object):

    def __init__(self, endog, exog, store_r=False, standardized=False,
                 ddof_std=0, ddof_model=0):
        '''

        standardized requires that there is no constant in exog

        Issues
        multivariate endog is partially possible, but not fully implemented
            currently only univariate endog is treated correctly in many methods

        possible extension:
            start from a pinv solution for initially included variables
        '''
        self.endog = endog
        self.exog = exog
        self.ddof_std = ddof_std
        self.ddof_model = ddof_model

        xy = np.column_stack((exog, endog))
        self.k_vars_x = exog.shape[1]
        if endog.ndim == 2:
            self.k_vars_y = endog.shape[1]
        else:
            self.k_vars_y = 1
        self.k_vars_all =  self.k_vars_y + self.k_vars_x
        self.nobs = xy.shape[0]
        self.mean_data = xy.mean(0)
        self.std_data = xy.std(ddof_std)
        if standardized: #zscore
            #xy[:,1:] /= xy[:,1:].std(0)  #if we had a constant in column 1
            xy /= np.sqrt((xy * xy).mean(0)) #
            xy = (xy - self.mean_data) / self.std_data
            self.ddof_model += 1   #add constant to df

        rs0 = np.dot(xy.T, xy) #/50
        self.rs0 = rs0
        self.is_exog = np.zeros(self.k_vars_all, bool)
        self.history = []
        self.rs_current = rs0.copy()

    def update_history(self):
        #add variables from the current model to the history
        #separate method so we can add things here

        self.history.append((self.is_exog.copy(),
                             self.rss,
                             self.params,
                            ))

    @property
    def rss(self):
        '''current residual sum of squares of endog variables

        '''
        ret = self.rs_current[-self.k_vars_y:, -self.k_vars_y:]
        if self.k_vars_y == 1:
            ret = np.squeeze(ret)[()]
        return ret

    @property
    def params(self):
        '''current parameter estimates of endog on included exog

        view
        '''
        #rows for all endog, cols for included exog
        ret = self.rs_current[-self.k_vars_y:, self.is_exog]
        return ret

    @property
    def df_resid(self):
        k_incl = self.is_exog.sum()

        return self.nobs - k_incl - self.ddof_model

    @property
    def scale2(self):
        return self.rs_current[-1,-1] / self.df_resid()

    @property
    def bse(self):
        '''current parameter estimates of endog on included exog

        view
        '''
        ret = self.normalized_cov_params
        ret *= self.scale2
        ret = np.sqrt(ret)
        return ret

    @property
    def normalized_cov_params(self):
        return self.rs_current[self.is_exog, self.is_exog]

    def sweep(self, k, update=True):
        '''sweep variable k

        Parameters
        ----------
        k : int
            index of the variable to be swept
        update : bool
            If True (default), then the attributes are updated. If False,
            then the instance stays unchanged and the new matrix is returned.

        Returns
        -------
        None or rs_next
            see update parameter

        Notes
        -----
        updates is mostly for checking results, we should get most of the
        results without full updating. See the rss_diff, params_new methods.

        '''
        #sweep function creates a copy
        rs_next = sweep(k, self.rs_current)
        if update:
            self.rs_current = rs_next
            self.is_exog[k] = ~self.is_exog[k]  #flip switch
            self.update_history()
        else:
            return rs_next

    def rss_diff(self, endog_idx=-1):
        '''change in rss when one of a variable is swept

        for now:
            look only at the effect on a single endog
            only case endog_idx=-1
        '''
        rr = self.rs_current
        #add_indicator = (~self.is_exog)
        add_indicator = ~self.is_exog[:self.k_vars_x] #for change in sign
        rssd = (rr[-1, :-1]**2 / np.diag(rr)[:-1])
        rssd *= np.sign(0.5 - add_indicator)
        return rssd

    def rss_new(self, endog_idx=-1):
        '''new values of rss when one of a variable is swept

        for now:
            look only at the effect on a single endog
            only case endog_idx=-1
        '''
        return self.rss + self.rss_diff(self, endog_idx=endog_idx)

    def ftest_sweep(self, endog_idx=-1):
        '''get f_test for sweeping a variable

        Warning: currently for adding only
        incomplete vectorization

        '''
        from scipy import stats #lazy for now

        #need to make the following conditional on is_endog, add or drop
        ssr_diff = self.rss_diff(endog_idx=endog_idx)
        #need to find larger/nesting model
        add_indicator = ~self.is_exog[:self.k_vars_x]
        ssr_full = self.rss + ssr_diff * add_indicator
        #add one variable, df_resid goes down
        df_full = self.df_resid - add_indicator
        df_diff = 1

        f_value = np.abs(ssr_diff) / df_diff / ssr_full * df_full
        p_value = stats.f.sf(f_value, df_diff, df_full)
        return f_value, p_value, (ssr_diff, df_diff, ssr_full, df_full)

    def params_new(self, endog_idx=-1):
        '''new parameters when one variable is swept

        rows correspond to variable that is swept
        columns are the variables as in exog

        for now:
            look only at the effect on a single endog
            only case endog_idx=-1

        '''
        kx = self.k_vars_x
        rr = self.rs_current
        params_own = (rr[-1, :-1] / np.diag(rr)[:-1]) #, None])
        params_own[self.is_exog[:self.k_vars_x]] = 0
        #is_exog = self.is_exog.copy()
        #the following works for variables that are in
        #row k corresponds to sweeping variable k
        #new parameters of variables are in columns
        params = rr[-1, :kx]-rr[-1, :kx][:,None] * rr[:kx, :kx] / np.diag(rr)[:kx,None]
        mask = np.repeat(self.is_exog[None,:self.k_vars_x], self.k_vars_x, axis=0)
        params[~mask] = 0
        #np.diag is mixing views versus copy across versions
        idx = np.arange(self.k_vars_x)
        params[idx, idx] = params_own
        #params = np.atleast_2d(params)
        return params

    def params_diff(self, endog_idx=-1):
        '''change in params when one variable is swept

        for now:
            look only at the effect on a single endog
            only case endog_idx=-1
        '''
        rr = self.rs_current
        params_current = rr[-1, :-1].copy()
        params_current[~self.is_exog[:-1]] = 0
        return params_current - self.params_new(endog_idx=endog_idx)

    def get_results(self):
        '''run OLS regression on current model and return results

        '''
        from statsmodels.regression.linear_model import OLS
        res = OLS(self.endog, self.exog[:, self.is_exog]).fit()
        return res
