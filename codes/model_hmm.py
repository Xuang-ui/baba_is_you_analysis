import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from scipy.special import logsumexp
from scipy.stats import norm
from joblib import Parallel, delayed


# ====== EM_HMM 的模型定义 ======

class EM_HMM:
    """毫秒为单位的船新版本"""
    TRANS_MASK =  np.array([
        # exe   pre   post  plan
        [ True,  True, False, True],   # from exe:  ->exe, ->pre, ->plan OK
        [ True,  True, False, True],   # from pre:  ->exe, ->pre, ->plan OK
        [ True, False,  True, True],   # from post: ->exe, ->post, ->plan OK
        [ True, False,  True, True],   # from plan: ->exe, ->post, ->plan OK
    ])

    def __init__(self, num_states = 4, data = 'linear', llik = 'ig', init_para = None, 
                 mu_min = -1, lam_max = 10000.0, mu_gap = 0.1):
        self.num_states = num_states
        self.init_para = self._set_para(init_para)
        self.para = self._copy_para(self.init_para)
        self.data_func = self._data_func(data)
        self.reverse_func = self._reverse_data_func(data)
        self.llik_func = self._llik_func(llik)
        self.updata_func = self._update_func(llik)

        self.mu_min, self.lam_max, self.mu_gap = mu_min, lam_max, mu_gap
    
    def _copy_para(self, params):
        return tuple(a.copy() for a in params)
    
    def reset_para(self):
        self.para = self._copy_para(self.init_para)
    
    @staticmethod
    def _data_func(data):
        def trans_linear(rt_series):
            return (np.array(rt_series/1000.0 - 0.25)).clip(1e-6, np.inf)
        
        def trans_log(rt_series):
            return np.log(0.004 * np.array(rt_series).clip(250, np.inf))
        
        return trans_linear if data == 'linear' else trans_log
    
    @staticmethod
    def _reverse_data_func(data):
        def reverse_linear(rt_series):
            return rt_series * 1000.0 + 250.0
        
        def reverse_log(rt_series):
            return np.exp(rt_series) * 250.0
        return reverse_linear if data == 'linear' else reverse_log
    
    @staticmethod
    def _llik_func(llik):

        def logp_ig(x, mu, lam):
            x[x<1e-6], mu_b, lam_b, x_b = 1e-6, mu[np.newaxis, :], lam[np.newaxis, :], x[:, np.newaxis]
            return 0.5 * np.log(lam_b) - 0.5 * np.log(2 * np.pi) - 1.5 * np.log(x_b) - (lam_b * (x_b - mu_b)**2) / (2 * x_b * mu_b**2)
        
        def logp_norm(x, mu, lam):
            x[x<1e-6], mu_b, lam_b, x_b = 1e-6, mu[np.newaxis, :], lam[np.newaxis, :], x[:, np.newaxis]
            return 0.5 * np.log(lam_b) - 0.5 * np.log(2 * np.pi) - 0.5 * lam_b * (x_b - mu_b) ** 2
        
        def logp_norm_cen(x, mu, lam):

            mu_b, lam_b, x_b = mu[np.newaxis, :], lam[np.newaxis, :], x[:, np.newaxis]
            log_emit = 0.5 * np.log(lam_b) - 0.5 * np.log(2 * np.pi) - 0.5 * lam_b * (x_b - mu_b) ** 2
            censored = (x <= 0.065).flatten()
            if censored.any():
                log_emit[censored] = norm.logcdf(-mu * np.sqrt(lam))
            return log_emit
        
        check_list = {'ig': logp_ig, 'norm': logp_norm, 'norm_cen': logp_norm_cen}
        return check_list.get(llik, logp_norm_cen)
    
    @staticmethod
    def _update_func(llik):

        def update_ig(rt_star, gamma, mu_old, lam_old):
            N_k = gamma.sum(0)
            mu_new = np.where(N_k > 1e-6, gamma.T @ rt_star / N_k, mu_old)
            inv_lam_new = (gamma.T @ (1.0 / rt_star) / N_k) - (1.0 / mu_new)
            lam_new = np.where(inv_lam_new > 1e-6, 1.0 / inv_lam_new, lam_old)
            return mu_new, lam_new

        def update_norm(rt_star, gamma, mu_old, lam_old):
            N_k = gamma.sum(0)
            mu_new = np.where(N_k > 1e-6, gamma.T @ rt_star / N_k, mu_old)
            
            diff_sq = (rt_star[:, np.newaxis] - mu_new[np.newaxis])**2
            lam_new = np.where(N_k > 1e-6, N_k / (gamma * diff_sq).sum(0), lam_old)
            return mu_new, lam_new
        
        def update_norm_cen(rt_star, gamma, mu_old, lam_old):

            N_k = gamma.sum(0)
            censored = (rt_star <= 0.065).flatten()
            sigma_old = 1/lam_old**0.5
            alpha = -mu_old / sigma_old
            mills = norm.pdf(alpha) / np.maximum(norm.cdf(alpha), 1e-20)
            E_x = mu_old - sigma_old * mills
            E_x2 = mu_old**2 + sigma_old**2 - mu_old * sigma_old * mills

            # censored
            x_filled = np.where(censored[:, np.newaxis], E_x, rt_star[:, np.newaxis])
            mu_new = np.where(N_k > 1e-6, (gamma * x_filled).sum(0) / N_k, mu_old)
            
            
            diff_sq = (rt_star[:, np.newaxis] - mu_new[np.newaxis])**2
            diff_sq = np.where(censored[:, np.newaxis], E_x2 - 2 * mu_new * E_x + mu_new**2, diff_sq)
            lam_new = np.where(N_k > 1e-6, N_k / (gamma * diff_sq).sum(0), lam_old)
            return mu_new, lam_new
        
        check_list = {'ig': update_ig, 'norm': update_norm, 'norm_cen': update_norm_cen}
        return check_list.get(llik, update_norm_cen)

    def _set_para(self, params = None):
        if params is None:
            A = np.stack([[0.6, 0, 0.4], [0, 0, 1], [0.3, 0.3, 0.4]])
            pi = np.array([0.0, 1.0, 0.0])
            mu_ig = np.array([50.0, 1500.0, 300.0]) * 0.001
            lam_ig = np.array([50.0, 50.0, 50.0]) * 0.001
            params = (A, pi, mu_ig, lam_ig)
        return params
    
    def _random_para(self, rt):
        A = np.random.dirichlet(np.ones(self.num_states), size=self.num_states)
        A = self._project_A(A, A)
        pi = np.array([0.0, 0.0, 0.0, 1.0])
        quantile = np.sort(np.random.rand(self.num_states))
        mu = self.data_func(np.quantile(rt, quantile))
        lamb = np.ones(self.num_states)
        random_para = (A, pi, mu, lamb)
        self.para = self._copy_para(random_para)

    def _project_A(self, A_raw, A_old):
        A_raw = A_raw * self.TRANS_MASK
        row_sum = A_raw.sum(axis=1, keepdims=True)
        return np.where(row_sum > 1e-6, A_raw / row_sum.clip(1e-6), A_old)
    
    def _project_mu(self, mu):
        mu = mu.copy()
        mu[0] = np.maximum(mu[0], self.mu_min)
        mu[1] = np.maximum(mu[1], mu[0] + self.mu_gap)
        mu[2] = np.maximum(mu[2], mu[0] + self.mu_gap)
        mu[3] = np.maximum(mu[3], np.maximum(mu[1], mu[2]) + self.mu_gap)
        return mu

    def estep(self, rt_star):
        A, pi, mu_ig, lam_ig = self.para
        T = len(rt_star)
        log_ep = self.llik_func(rt_star, mu_ig, lam_ig)
        log_A = np.log(np.maximum(A, 1e-300))
        log_pi = np.log(np.maximum(pi, 1e-300))

        log_alpha = np.zeros((T, self.num_states))
        log_alpha[0, :] = log_pi + log_ep[0]
        for t in range(1, T):
            log_alpha[t] = log_ep[t] + logsumexp(log_alpha[t-1].reshape(-1, 1) + log_A, axis = 0)
        log_likelihood = logsumexp(log_alpha[T-1])
        log_beta = np.zeros((T, self.num_states))
        for t in range(T-2, -1, -1):
            log_beta[t] = logsumexp(log_A + log_ep[t+1] + log_beta[t+1], axis = 1)
        log_gamma = log_alpha + log_beta - log_likelihood
        gamma = np.exp(log_gamma).clip(1e-10, np.inf)
        log_xi = np.zeros((T-1, self.num_states, self.num_states))
        for t in range(T-1):
            log_xi[t] = log_alpha[t].reshape(-1, 1) + log_A + log_ep[t+1] + log_beta[t+1] - log_likelihood
        xi = np.exp(log_xi).clip(1e-10, np.inf)
        return gamma, xi, log_likelihood

    def mstep(self, rt_star, gamma, xi):
        A_old, pi, mu_old, lam_old = self.para
        gamma_sum = gamma[:-1].sum(0)
        A_raw = np.where(gamma_sum[:, np.newaxis] > 1e-6, xi.sum(0) / gamma_sum[:, np.newaxis], A_old)
        A_new = self._project_A(A_raw, A_old)
        mu_new, lam_new = self.updata_func(rt_star, gamma, mu_old, lam_old)
        mu_new = self._project_mu(mu_new)
        lam_new = np.minimum(lam_new, self.lam_max)
        return A_new, pi, mu_new, lam_new


    def __call__(self, rt_series, n_start = 20, max_iter=1000, tolerance=1e-4):
        rt_star = self.data_func(rt_series)

        best_ll, best_result = -np.inf, None
        for r in range(n_start):
            self._random_para(rt_star)
            log_likelihoods = []
            try:
                for i in range(max_iter):
                    gamma, xi, ll = self.estep(rt_star)
                    log_likelihoods.append(ll)
                    if i > 0 and abs(log_likelihoods[-1] - log_likelihoods[-2]) < tolerance:
                        # print(f"EM 算法在第 {i+1} 步收敛。")
                        break
                    self.para = self.mstep(rt_star, gamma, xi)
                final_gamma, _, final_ll = self.estep(rt_star)
                pred = final_gamma.argmax(1)
                if final_ll > best_ll:
                    best_ll = final_ll
                    best_result = (self._copy_para(self.para), final_ll, final_gamma, pred)
            except Exception as e:
                print(f"EM 算法在第 {r+1} 次初始化时出错: {e}")
        return best_result
    
# ====== HMM 模型拟合 ======
def HMM_Result(df, model, RT_colname = 'Before'):
    """地图，被试"""

    if 'pred_DD' not in df.columns:
        paras, llik, gamma, pred_pd = model(df[RT_colname])
        gamma = gamma.round(3)
        df['pred_Exe'] = gamma[:, 0]
        df['pred_Pre'] = gamma[:, 1]
        df['pred_Post'] = gamma[:, 2]
        df['pred_Plan'] = gamma[:, 3]
        df['pred_DD'] = gamma[:, 0] * 0 + gamma[:, 1] * 1 + gamma[:, 2] * 1 + gamma[:, 3] * 2
        df['pred_Max'] = pred_pd
    return df


def _fit_one(map_name, uid, rt_array, data_type, llik_type, n_start):
    """单个 (map, uid) 的 HMM 拟合，每个 worker 独立创建模型实例"""
    model = EM_HMM(data=data_type, llik=llik_type)
    try:
        paras, llik, gamma, pred_pd = model(rt_array, n_start=n_start)
        gamma = gamma.round(3)
        return map_name, uid, gamma, pred_pd, True
    except Exception as e:
        print(f"Failed: {map_name}/{uid}: {e}")
        return map_name, uid, None, None, False

def _fit_one_with_param(map_name, uid, rt_array, data_type, llik_type, n_start, init_para):
    """单个 (map, uid) 的 HMM 拟合，每个 worker 独立创建模型实例"""
    model = EM_HMM(data=data_type, llik=llik_type, init_para=init_para)
    try:
        (A, mu, lam), llik, gamma, pred_pd = model(rt_array, n_start=n_start)
        gamma = gamma.round(3)
        return map_name, uid, gamma, pred_pd, A, mu, lam, llik, True
    except Exception as e:
        print(f"Failed: {map_name}/{uid}: {e}")
        return map_name, uid, None, None, None, None, None, None, False


def HMM_Result_Parallel(env, map_names, data_type='log', llik_type='norm',
                         RT_colname='Before', n_jobs=-4, n_start=20, verbose=10):
    """并行批量 HMM 拟合，结果写回 env.em._grouped_data"""

    # 1) 收集待拟合任务
    tasks = []
    for map_name in map_names:
        for (mn, uid), df in env.em.iter_epoch(map_name=map_name):
            if 'pred_DD' not in df.columns:
                tasks.append((mn, uid, df[RT_colname].values))

    if not tasks:
        print("所有数据已拟合，无需重复计算。")
        return env.em.rebuild_total_df()

    print(f"共 {len(tasks)} 个 (map, uid) 待拟合，使用 n_jobs={n_jobs}")

    # 2) 并行执行
    results = Parallel(n_jobs=n_jobs, backend='loky', verbose=verbose)(
        delayed(_fit_one_with_param)(m, u, rt, data_type, llik_type, n_start)
        for m, u, rt in tasks
    )

    # 3) 写回结果
    n_success, n_fail = 0, 0
    param_records = []
    for map_name, uid, gamma, pred_pd, A, mu, lam, llik, success in results:
        if not success:
            n_fail += 1
            continue
        df = env.em._grouped_data[map_name][uid]
        df['pred_Exe']  = gamma[:, 0]
        df['pred_Pre']  = gamma[:, 1]
        df['pred_Post'] = gamma[:, 2]
        df['pred_Plan'] = gamma[:, 3]
        df['pred_DD']   = gamma[:, 0]*0 + gamma[:, 1]*1 + gamma[:, 2]*1 + gamma[:, 3]*2
        df['pred_Max']  = pred_pd
        n_success += 1

        sigma = 1.0 / np.sqrt(lam)
        param_records.append({
            'Map': map_name, 'Uid': uid, 'llik': llik,
            'mu_exe': mu[0], 'mu_pre': mu[1], 'mu_post': mu[2], 'mu_plan': mu[3],
            'sigma_exe': sigma[0], 'sigma_pre': sigma[1], 'sigma_post': sigma[2], 'sigma_plan': sigma[3],
            'A_exe_exe': A[0,0], 'A_exe_pre': A[0,1], 'A_exe_plan': A[0,3],
            'A_pre_exe': A[1,0], 'A_pre_pre': A[1,1], 'A_pre_plan': A[1,3],
            'A_post_exe': A[2,0], 'A_post_post': A[2,2], 'A_post_plan': A[2,3],
            'A_plan_exe': A[3,0], 'A_plan_post': A[3,2], 'A_plan_plan': A[3,3],
        })       
    param_df = pd.DataFrame(param_records) 
    print(f"完成: {n_success} 成功, {n_fail} 失败")
    return env.em.rebuild_total_df(), param_df

def recover_params(env, map_names, data_type='log', RT_colname='Before'):
    """从已有的 gamma 列直接计算参数"""
    model = EM_HMM(data=data_type, llik='norm')  # 只用 data_func
    records = []
    
    for map_name in map_names:
        for (mn, uid), df in env.em.iter_epoch(map_name):
            if 'pred_Exe' not in df.columns:
                continue
            x = model.data_func(df[RT_colname].values)
            gamma = df[['pred_Exe', 'pred_Pre', 'pred_Post', 'pred_Plan']].values
            N_k = np.maximum(gamma.sum(0), 1e-8)
            
            # mu, sigma — 用 soft gamma 加权，和 M-step 完全等价
            mu = (gamma.T @ x) / N_k
            diff_sq = (x[:, None] - mu[None, :]) ** 2
            sigma = np.sqrt((gamma * diff_sq).sum(0) / N_k)
            # A — 用 hard 标签的连续转移近似
            A = gamma[:-1].T @ gamma[1:]          # (4, 4): sum of γ_t(i) * γ_{t+1}(j)
            row_sum = gamma[:-1].sum(0)                # (4,):   sum of γ_t(i)
            A = A / row_sum[:, None].clip(1e-10)
            A = model._project_A(A, A)  # 投影到合法转移矩阵空间

            pi = get_station_pi(A)
            
            records.append({
                'Map': mn, 'Uid': uid,
                'mu_exe': mu[0], 'mu_pre': mu[1], 'mu_post': mu[2], 'mu_plan': mu[3],
                'sigma_exe': sigma[0], 'sigma_pre': sigma[1], 'sigma_post': sigma[2], 'sigma_plan': sigma[3],
                **{f'A_{i}{j}': A[i,j] for i in range(4) for j in range(4)}, 
                'pi_exe': pi[0], 'pi_pre': pi[1], 'pi_post': pi[2], 'pi_plan': pi[3],
            })
    return pd.DataFrame(records)

        
def get_station_pi(matrix):
    pi = np.array([0., 0., 0., 1.])
    matrix = matrix / matrix.sum(1, keepdims=True).clip(1e-6)
    for i in range(10000):
        pi_new = pi @ matrix
        if np.linalg.norm(pi_new - pi) < 1e-10:
            break
        pi = pi_new
    return pi

# ===== HMM 结构图绘制 ======
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import Ellipse, FancyArrowPatch

def ellipse_boundard(center, width, height, angle):
    cx, cy, a, b = center[0], center[1], width/2, height/2
    t = np.sqrt(a**2 * np.cos(angle)**2 + b**2 * np.sin(angle)**2)
    return (cx + t * np.cos(angle), cy + t * np.sin(angle))

def get_arrow(source, target, width, height):
    dx, dy = target[0] - source[0], target[1] - source[1]
    angle = np.arctan2(dy, dx)
    start_p = ellipse_boundard(source, width, height, angle)
    end_p = ellipse_boundard(target, width, height, angle + np.pi)
    return start_p, end_p

def get_circular(source, angle, diff, width, height):
    start_p = ellipse_boundard(source, width, height, angle - np.pi/6 * diff)
    end_p = ellipse_boundard(source, width, height, angle + np.pi/6 * diff)
    return start_p, end_p

def draw_arrow(start_p, end_p, rad, color, width):
    return FancyArrowPatch(start_p, end_p,
                           connectionstyle=f"arc3,rad={rad}",
                            arrowstyle='->',
                            mutation_scale=20,
                            color=color,
                            linewidth=width)

def draw_hmm_structure(matrix, e_width = 0.8, e_height = 0.6, saving = None):
    # 定义节点位置和颜色
    Exe, Pre, Plan, Post = "Routine\nExecution", "Pre-Deliberative\nPreparation", "Deliberative\nPlanning", "Post-Deliberative\nStablization"
    nodes = [Exe, Pre, Post, Plan]
    pos = {Exe: (1, 0), Pre: (0, 1), Post: (2, 1),  Plan: (1, 2)}
    colors = {Exe: '#c8b9e0', Pre: '#95d1b0', Plan: '#f0e4a0', Post: '#95d1b0'}
    station_distribution = get_station_pi(matrix)
    station_pi = {node: station_distribution[i] for i, node in enumerate(nodes)}
    

    G = nx.DiGraph()
    [G.add_node(node, pos=p) for node, p in pos.items()]
    edges_with_weights = [(nodes[i], nodes[j], matrix[i, j]) for i in range(4) for j in range(4) if matrix[i, j] > 0.01]
    [G.add_edge(s, t, weight=w) for s, t, w in edges_with_weights]

    plt.figure(figsize=(12, 9))
    ax = plt.gca()
    
    # 绘制椭圆节点
    for node, (x, y) in pos.items():
        ellipse = Ellipse((x, y), width=e_width, height=e_height, facecolor=colors[node], edgecolor='black', linewidth=2)
        ax.add_patch(ellipse)
        ax.text(x, y, f"{node}\n{station_pi[node]*100:.1f}%", ha='center', va='center',fontsize=17, fontweight='bold', wrap=True)
    
    # 只为真实存在的边绘制权重标签
    for source, target, data in G.edges(data=True):
        weight = data['weight'] 
        edge_color = colors[source]  # 边的颜色与出发节点一致
        line_width = weight * 25  # 调整线宽比例，让差异更明显
        
        if source == target:  # 自环 - 手动绘制带偏移的自环            
            # 根据节点位置确定自环的方向和偏移 - 仿照Exe的模式
            if source == Exe:  # bottom - 向下的自环
                start_point, end_point = get_circular(pos[source], 0, 1, e_width, e_height)
                label_offset = (0.65, 0)
            elif source == Pre:  # left - 向左的自环，仿照Exe的模式
                start_point, end_point = get_circular(pos[source], -np.pi/2, 1, e_width, e_height)
                label_offset = (-0.2, -0.5)
            elif source == Plan:  # top - 向上的自环，仿照Exe的模式
                start_point, end_point = get_circular(pos[source], np.pi, 1, e_width, e_height)
                label_offset = (-0.65, 0)
            elif source == Post:  # right - 向右的自环，仿照Exe的模式
                start_point, end_point = get_circular(pos[source], np.pi/2, 1, e_width, e_height)
                label_offset = (0.2, 0.5)
            
            arrow = FancyArrowPatch(start_point, end_point,
                                  connectionstyle="arc3,rad=1",  # 增大弧度让自环更圆
                                  arrowstyle='->', 
                                  mutation_scale=20,  # 增大箭头
                                  color=edge_color, 
                                  linewidth=line_width)  # 增加最小线宽
            ax.add_patch(arrow)
            
            # # 标注自环权重
            plt.text(pos[source][0] + label_offset[0], pos[source][1] + label_offset[1], 
                    f'{weight*100:.1f}%', fontsize=14, fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.3", facecolor=edge_color, alpha=0.5, edgecolor=edge_color),
                    ha='center', va='center')
                    
        else:  # 普通边
            start_point, end_point = get_arrow(pos[source], pos[target], e_width, e_height)
            arrow = FancyArrowPatch(start_point, end_point,
                                  connectionstyle='arc3, rad=0.2',
                                  arrowstyle='->', 
                                  mutation_scale=20, 
                                  color=edge_color, 
                                  linewidth=max(3, line_width))
            ax.add_patch(arrow)
            
            # 计算边中点位置标注权重
            source_pos = pos[source]
            target_pos = pos[target]
            mid_x = (source_pos[0] + target_pos[0]) / 2
            mid_y = (source_pos[1] + target_pos[1]) / 2
            
            # 为反向边调整偏移避免重叠
            offset = 0.1
            # 检查是否有反向边
            reverse_edge_exists = G.has_edge(target, source)
            if reverse_edge_exists and (source, target) < (target, source):
                # 这是"较小"的边，偏移到一侧
                offset = -offset
         
            plt.text(mid_x + offset, mid_y + offset, 
                    f'{weight*100:.1f}%', fontsize=14, fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=edge_color, alpha=0.5, edgecolor=edge_color),
                    ha='center', va='center')

    # plt.title("4-State HMM Transition Structure with Weights (%)", pad=30, fontsize=14, fontweight='bold')
    
    # 调整显示范围，为自环留出更多空间
    plt.xlim(-0.5, 2.5)
    plt.ylim(-0.3, 2.3)
    plt.title(saving)
    plt.axis('off')
    
    # 保存为PDF
    if saving is not None:
        
        plt.savefig(f'../figure/hmm_{saving}.pdf', format='pdf', dpi=300, transparent=True)
        print(f"HMM结构图已保存为 ../figure/hmm_{saving}.pdf")
    plt.show()