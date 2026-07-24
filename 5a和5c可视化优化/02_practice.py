# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import warnings
from scipy import stats
from scipy.stats import mannwhitneyu, chi2_contingency

warnings.filterwarnings('ignore')

BASE_DIR = r"C:\Users\32122\Desktop"
DATA_PATH = os.path.join(BASE_DIR,"data", "cancer_data_eng.csv")
IMG_DIR = os.path.join(BASE_DIR,"img")
RESULTS_DIR = os.path.join(BASE_DIR,"results")

os.makedirs(IMG_DIR,exist_ok=True)
os.makedirs(RESULTS_DIR,exist_ok=True)

print("\n[0] 加载数据...")
df = pd.read_csv(DATA_PATH, low_memory=False, encoding='latin-1')
# 创建目标变量: VIVO=1 (alive), MORTO=0 (dead)
# 使用 map 而非 == 比较，避免缺失值被误判为 MORTO(0)
df['target'] = df['Status.Vital'].map({'VIVO': 1, 'MORTO': 0})
# 仅保留目标变量非缺失的样本
df_model = df.dropna(subset=['target']).copy()

print(f"原始样本量：{len(df):,}")
print(f"有标签样本：{len(df_model):,}")
print(f"VIVO(存活)：{(df_model['target'] ==1).sum():,}({(df_model['target'] == 1).mean()*100:.2f}%)")
print(f"MORTO(死亡)：{(df_model['target'] ==0).sum():,}({(df_model['target'] == 0).mean()*100:.2f}%)")

print("\n" + "=" * 70)
print("步骤 1: 特征分类")
print("=" * 70)

# 识别数值型和分类型候选
all_cols = df_model.columns.tolist()
exclude_cols = ['Patient.Code', 'target', 'Status.Vital',
                'Date.of.Birth', 'Date.of.Death', 'Date.of.Last.Contact',
                'Date.of.Diagnostic']

# 数值型候选
numeric_candidates = ['Age', 'Code.Profession', 'Code.of.Morphology', 'year']

# 分类型候选 (根据领域知识和低缺失率筛选)
categorical_candidates = [
    'Gender', 'Raca.Color', 'Diagnostic.means', 'Extension',
    'Laterality', 'State.Civil', 'Degree.of.Education',
    'Description.of.Topography', 'Topography.Code',
    'Morphology.Description', 'Description.of.Disease',
    'Illness.Code', 'Child.Illness.Description',
    'Youth.Adult.Illness.Description', 'Type.of.Death',
    'Distant.metastasis', 'Nationality', 'Naturality.State'
]

# 过滤: 确保列存在且在排除列表之外
numeric_features = [col for col in numeric_candidates if col in df_model.columns and col not in exclude_cols]
categorical_features = [col for col in categorical_candidates
                        if col in df_model.columns and col not in exclude_cols]

# Bonferroni 校正: 在所有特征(数值+分类)上统一校正，与教学文档一致
total_n_features = len(numeric_features) + len(categorical_features)

print(f"\n 数值型特征：{numeric_features}")
print(f" 分类型特征：{categorical_features}")
print(f"总数征数（用于Bonferroni矫正）：{total_n_features}")

# 辅助函数: 判断正态性 (对大样本使用偏度 + D'Agostino-Pearson)
def check_normality_practical(data,sample_limit=5000):
    data_clean = data.dropna()
    if len(data_clean) < 30:
        return False,"样本量不足"
    
    # 如果数据太大，抽样做正式检验
    skewness = data_clean.skew()
    
    if len(data_clean) > sample_limit:
        data_test = data_clean.sample(sample_limit,random_state=42)
    else:
        data_test = data_clean

    # 偏度绝对值 < 0.5 视为近似正态
    if abs(skewness) < 0.5:
        return True,f"近似正态（偏度={skewness:.3f}"
    elif abs(skewness) < 1.0:
        # 边缘情况: 用 D'Agostino-Pearson 检验辅助判断
        try:
           _,p_value = stats.normaltest(data_test) 
           if p_value > 0.05:
                return True,f"正态(p={p_value:.4f})"
           else:
                return False,f"非正态（偏度={skewness:.3f},p={p_value:.4f})"
        except Exception:
            return False,f"非正态（偏度={skewness:.3f})"
    else:
        #偏度绝对值 <= 1.0 视为非正态
        return False,f"非正态（偏度={skewness:.3f})"
    
numerical_results = []
for col in numeric_features:
    #成对删除缺失值，只要coL和target有一个缺失就删除
    data = df_model[[col,'target']].dropna()
    #最小总样本量
    if len(data) < 30:
        continue
    #布尔索引分组 data.loc[行选择器，列选择器]
    #结果：一个series
    group_vivo = data.loc[data['target'] == 1,col]
    group_morto = data.loc[data['target'] == 0,col]
    #统计监测最小样本要求
    if len(group_vivo) < 5 or len(group_morto) < 5:
        continue
    #正态性判断
    is_normal,norm_note = check_normality_practical(data[col])
    if is_normal:
        #正态分布，使用t检验
        #独立样本t检验有个重要前提：两组方差应该相等（方差齐性）
        
        #方差齐性检验：Levene检验
        #原假设：两组方差相等
        lenven_stat,levene_p = stats.levene(group_vivo,group_morto)
        #统计量，p值 
        equal_var = levene_p > 0.05
        #如果levene_p > 0.05 不拒绝原假设，认为方差相等，使用Student's t 检验
        #如果levene_p <= 0.05 拒绝原假设，认为方差不等，使用Welch's t 检验
        
        #独立样本t检验
        #原假设：两组均值相等
        t_stat,p_value = stats.ttest_ind(group_vivo,group_morto,equal_var=equal_var)
        test_used = "T-test (独立样本t检验)"

        #Cohen's d 效应量
        n1,n2 = len(group_vivo),len(group_morto)
        s1,s2 = group_vivo.std(),group_morto.std()
        pooled_std = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))/(n1+n2-2)
        effect_size = abs((group_vivo.mean() - group_morto.mean())/pooled_std) if pooled_std > 0 else 0 
        effect_type = "Cohen's d"

    else:
        #非正态分布，使用Mann-Whitney U检验
        #原假设：两组分布相同
        u_stat,p_value =mannwhitneyu(group_vivo,group_morto,alternative="two-sided")
        test_used = "Mann-Whitney U检验"

        #Rank-Biserial correlation 效应量
        n1,n2 = len(group_vivo),len(group_morto)
        effect_size = abs(1-(2*u_stat)/(n1*n2))
        effect_type = "Rank-Biserial correlation"

    # 判断显著性 (Bonferroni 校正)
    mean_v = group_vivo.mean()
    mean_m = group_morto.mean()
    median_v = group_vivo.median()
    median_m = group_morto.median()

    numerical_results.append({
        "Feature": col,
        "N":len(data),
        "Test":test_used,
        "Normality": norm_note,
        "Mean_VIVO": mean_v,
        "Mean_MORTO": mean_m,
        "Median_VIVO": median_v,
        "Median_MORTO": median_m,
        'Statistic': t_stat if is_normal else u_stat,
        "Test_Used": test_used,
        "P_Value": p_value,
        "Effect_Size": effect_size,
        "Effect_Type": effect_type,
        "Significant_0.05":"Yes" if p_value < 0.05 else "No",  
        "Significant_Bonf":"Yes" if p_value < 0.05 / total_n_features else "No"
    })

    print(f"\n  ▶ {col}")
    print(f"     检验方法: {test_used}  |  正态性判断: {norm_note}")
    print(f"     VIVO: μ={mean_v:.2f}, M={median_v:.1f}  |  MORTO: μ={mean_m:.2f}, M={median_m:.1f}")
    print(f"     p_value = {p_value:.6e}  |  效应量({effect_type}) = {effect_size:.4f}")

num_df = pd.DataFrame(numerical_results)

categorical_results = []

for col in categorical_features:
    data = df_model[[col,'target']].dropna()
    #双括号，返回DataFrame(两列)，而不是Series(一列)
    
    if len(data) < 30:
        continue
    
    #统计每个类别的个数
    value_counts = data[col].value_counts()
    #过滤掉样本量小于5的类别
    valid_categories = value_counts[value_counts >= 5].index
        #valid_categories中只有有效类别
    data_filtered = data[data[col].isin(valid_categories)]
    
    #第二次样本量检查
    if len(data) < 30:
        continue

    #构建列联表
    contingency = pd.crosstab(data_filtered[col],data_filtered['target'])
        #pd.crosstab(index,columns)
    #列联表的维度检查
    if contingency.shape[0] < 2 or contingency.shape[1] <2:
        continue
    #调用chi2_contingency
    try:
        chi2_stat,p_value,dof,expected = chi2_contingency(contingency)
            #scipy.stat.contingency(observed)是卡方独立性检验函数
            #chi2_stat是卡方统计量，p_value是p值，dof是自由度，expected是期望频数表
    except Exception:
        continue

    #Cramér's V 效应量
    n_total = contingency.values.sum()
    phi2 = chi2_stat / n_total
    k = min (contingency.shape)-1
    cramer_v = np.sqrt(phi2 / k) if k > 0 else 0

    # 判断显著性 (Bonferroni 校正
    categorical_results.append({
        'Feature': col,
        'N': len(data_filtered),
        'Categories': contingency.shape[0],
        'Chi2': chi2_stat,
        'P_Value': p_value,
        'Cramér_V': cramer_v,
        'Significant_0.05': 'Yes' if p_value < 0.05 else 'No',
        'Significant_Bonf': 'Yes' if p_value < 0.05 / total_n_features else 'No'
    })

    print(f"\n  ▶ {col}")
    print(f"     有效类别数: {contingency.shape[0]}")
    print(f"     χ² = {chi2_stat:.2f}, p = {p_value:.6e}")
    print(f"     Cramér's V = {cramer_v:.4f}")

cat_df = pd.DataFrame(categorical_results)



# 合并数值和分类结果
all_results = []

for _, row in num_df.iterrows():
    all_results.append({
        'Feature': row['Feature'],
        'Type': '数值型',
        'Test': row['Test'],
        'P_Value': row['P_Value'],
        'Effect_Size': row['Effect_Size'],
        'Effect_Type': row['Effect_Type'],
        'Significant_0.05': row['Significant_0.05'],
        'Significant_Bonf': row['Significant_Bonf']
    })

for _, row in cat_df.iterrows():
    all_results.append({
        'Feature': row['Feature'],
        'Type': '分类型',
        'Test': '卡方检验',
        'P_Value': row['P_Value'],
        'Effect_Size': row['Cramér_V'],
        'Effect_Type': "Cramér's V",
        'Significant_0.05': row['Significant_0.05'],
        'Significant_Bonf': row['Significant_Bonf']
    })

summary_df = pd.DataFrame(all_results).sort_values('P_Value')

print(f"\n  ▶ 共分析 {len(all_results)} 个特征:")
print(f"     数值型: {len(num_df)}  |  分类型: {len(cat_df)}")
print(f"\n  ▶ 在 α=0.05 水平显著: {summary_df['Significant_0.05'].value_counts().get('Yes', 0)} 个")
print(f"  ▶ Bonferroni 校正后显著: {summary_df['Significant_Bonf'].value_counts().get('Yes', 0)} 个")

print(f"\n  ▶ 按 p 值排序的显著变量列表:")
sig_df = summary_df[summary_df['Significant_0.05'] == 'Yes']
print(f"     {'特征':<30} {'类型':<8} {'检验方法':<22} {'p值':<14} {'效应量':<10}")
print(f"     {'-'*30} {'-'*8} {'-'*22} {'-'*14} {'-'*10}")
for _, row in sig_df.iterrows():
    print(f"     {row['Feature']:<30} {row['Type']:<8} {row['Test']:<22} {row['P_Value']:<14.6e} {row['Effect_Size']:<10.4f}")

# --- 图 5a: P-value 对比柱状图 ---
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# 数值特征 p-value
if len(num_df) > 0:
    # 绘图前置
    num_plot = num_df.sort_values('P_Value')
    height_arr = -np.log10(num_plot['P_Value'].values)
    # 设定画布Y轴上限（表格最高点）
    y_max = 300
    # 判定阈值：超过该值视为p≈0
    cut_threshold = y_max
    # 核心逻辑：p≈0则强制高度等于画布最高点
    # np.where(条件, 满足时取值, 不满足取值)
    height_fixed = np.where(height_arr >= cut_threshold, y_max, height_arr)

    # 可选：打印提示哪些特征被强制顶到最高
    mask = height_arr >= cut_threshold
    if mask.any():
        print("以下特征p趋近0，柱子已强制拉到图表最高点：")
        print(num_plot.loc[mask, "Feature"].tolist())

    # 绘图
    colors_num = ['#e74c3c' if p < 0.05 else '#3498db' for p in num_plot['P_Value']]
    ax = axes[0]
    bars = ax.bar(
        range(len(num_plot)),
        height_fixed,  # 使用截断后的高度数组
        width=0.6,
        color=colors_num,
        edgecolor='white'
    )
    # 固定Y轴范围，保证最高点统一
    ax.set_ylim(bottom=0, top=y_max)
    ax.grid(axis="y", alpha=0.3)

    # 红线标注α=0.05
    threshold_y = -np.log10(0.05)
    ax.axhline(y=threshold_y, color='red', linestyle='--', linewidth=1.5,
            label=f'α=0.05 (-log10={threshold_y:.2f})')

    ax.set_xticks(range(len(num_plot)))
    ax.set_xticklabels(num_plot['Feature'].values, rotation=30, ha='right')
    ax.set_ylabel('-log10(p-value)', fontsize=11)
    ax.set_title('Numerical Features: Statistical Significance', fontsize=13, fontweight='bold')
    ax.legend(fontsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

# 分类特征 p-value
if len(cat_df) > 0:
    # 绘图前置
    cat_plot = cat_df.sort_values('P_Value')
    height_arr = -np.log10(cat_plot['P_Value'].values)
    # 设定画布Y轴上限（表格最高点）
    y_max = 300
    # 判定阈值：超过该值视为p≈0
    cut_threshold = y_max
    # 核心逻辑：p≈0则强制高度等于画布最高点
    # np.where(条件, 满足时取值, 不满足取值)
    height_fixed = np.where(height_arr >= cut_threshold, y_max, height_arr)
    # 可选：打印提示哪些特征被强制顶到最高
    mask = height_arr >= cut_threshold
    if mask.any():
        print("以下特征p趋近0，柱子已强制拉到图表最高点：")
        print(cat_plot.loc[mask, "Feature"].tolist())

    colors_cat = ['#e74c3c' if p < 0.05 else '#3498db' for p in cat_plot['P_Value']]
    ax = axes[1]
    bars = ax.bar(range(len(cat_plot)), height_fixed,
                  color=colors_cat, edgecolor='white')
    ax.axhline(y=-np.log10(0.05), color='red', linestyle='--', linewidth=1.5,
               label=f'α=0.05 (-log10={-np.log10(0.05):.2f})')
    # 固定Y轴范围，保证最高点统一
    ax.set_ylim(bottom=0, top=y_max)
    ax.grid(axis="y", alpha=0.3)
    
    ax.set_xticks(range(len(cat_plot)))
    ax.set_xticklabels(cat_plot['Feature'].values, rotation=30, ha='right')
    ax.set_ylabel('-log10(p-value)', fontsize=11)
    ax.set_title('Categorical Features: Chi-square Significance', fontsize=13, fontweight='bold')
    ax.legend(fontsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

plt.suptitle('Statistical Significance Overview', fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "05a_pvalue_comparison.png"), dpi=150, bbox_inches='tight')
# plt.close()
print("  [图] 05a_pvalue_comparison.png → p值对比图已保存")

# --- 图 5b: 效应量对比图 ---
if len(all_results) > 0:
    fig, ax = plt.subplots(figsize=(12, 6))
    plot_df = summary_df.sort_values('Effect_Size', ascending=True)

    colors_effect = ['#e74c3c' if row['Effect_Size'] > 0.3
                     else ('#f39c12' if row['Effect_Size'] > 0.1 else '#3498db')
                     for _, row in plot_df.iterrows()]

    bars = ax.barh(range(len(plot_df)), plot_df['Effect_Size'].values,
                   color=colors_effect, edgecolor='white')
    ax.set_yticks(range(len(plot_df)))
    ax.set_yticklabels(plot_df['Feature'].values, fontsize=9)
    ax.set_xlabel('Effect Size', fontsize=11)
    ax.set_title('Feature Effect Sizes (Numerical & Categorical)', fontsize=13, fontweight='bold')

    # 效应量参考线
    ax.axvline(x=0.1, color='gray', linestyle=':', alpha=0.7, label='Small (0.1)')
    ax.axvline(x=0.3, color='orange', linestyle='--', alpha=0.7, label='Medium (0.3)')
    ax.axvline(x=0.5, color='red', linestyle='--', alpha=0.7, label='Large (0.5)')
    ax.legend(fontsize=9)

    for bar, val in zip(bars, plot_df['Effect_Size'].values):
        ax.text(val + 0.005, bar.get_y() + bar.get_height() / 2,
                f'{val:.4f}', va='center', fontsize=8)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "05b_effect_size_comparison.png"), dpi=150, bbox_inches='tight')
    # plt.close()
    print("  [图] 05b_effect_size_comparison.png → 效应量对比图已保存")

# --- 图 5c: p值 vs 效应量散点图 ---
import numpy as np
from matplotlib.lines import Line2D

if len(all_results) >= 3:
    fig, ax = plt.subplots(figsize=(12, 7))
    Y_CAP = 300  # 匹配你当前图Y轴上限300
    
    # 1. 预处理：按Effect_Size升序排序，生成序号映射
    summary_df = summary_df.sort_values("Effect_Size", ascending=False).reset_index(drop=True)
    # 生成序号 1,2,3...
    summary_df["rank_id"] = summary_df.index + 1
    # 构建序号-特征名字典，用于右下角图例
    rank_name_map = dict(zip(summary_df["rank_id"], summary_df["Feature"]))
    
    # 2. 校正Y轴，解决p=0为-inf丢失点
    summary_df['y_plot'] = np.where(
        summary_df['P_Value'] <= 0,
        Y_CAP,
        -np.log10(summary_df['P_Value'])
    )

    # 3. 绘制散点 + 只标注数字序号（不再显示长特征名）
    for _, row in summary_df.iterrows():
        color = '#e74c3c' if row['Type'] == '数值型' else '#2ecc71'
        size = 80 if row['Significant_0.05'] == 'Yes' else 40
        marker = 'o' if row['Type'] == '数值型' else 's'
        
        ax.scatter(
            row['Effect_Size'], row['y_plot'],
            c=color, s=size, marker=marker, alpha=0.7, edgecolors='gray', linewidths=0.5
        )
        # 只标注排序数字，彻底解决文字重叠
        ax.annotate(
            str(row["rank_id"]),
            xy=(row['Effect_Size'], row['y_plot']),
            fontsize=7, ha='center', va='bottom',
            xytext=(0, 4), textcoords='offset points'
        )

    # 辅助线
    ax.axhline(y=-np.log10(0.05), color='red', linestyle='--', linewidth=1, label=r'$\alpha$ = 0.05')
    ax.axvline(x=0.1, color='gray', linestyle=':', alpha=0.7, label='Small effect (0.1)')
    ax.axvline(x=0.3, color='orange', linestyle='--', alpha=0.7, label='Medium effect (0.3)')

    # 基础分类图例（数值/分类/不显著）
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', markersize=8, label='Numerical'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor='#2ecc71', markersize=8, label='Categorical'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=8, alpha=0.5, label='Not significant')
    ]
    leg1 = ax.legend(
        handles=legend_elements + ax.get_legend_handles_labels()[0][-3:],
        fontsize=8, loc='upper left',
        bbox_to_anchor=(0.02, 0.92)
    )
    ax.add_artist(leg1)  # 保留第一个图例，避免被覆盖

    # 4. 右下角新增【序号-特征映射图例】
    rank_legend_elems = []
    for rid, fname in rank_name_map.items():
        rank_legend_elems.append(
            Line2D([], [], marker='', linestyle='', label=f"{rid}: {fname}")
        )
    ax.legend(
        handles=rank_legend_elems,
        fontsize=7,
        loc='lower right',
        title="Rank ID - Feature Name",
        title_fontsize=8
    )

    # 坐标轴、标题、边界
    ax.set_xlabel('Effect Size', fontsize=11)
    ax.set_ylabel('-log10(p-value)', fontsize=11)
    ax.set_title(
        'P-value vs Effect Size: "Statistical vs Practical" Significance',
        fontsize=13, fontweight='bold'
    )
    ax.set_ylim(bottom=0, top=Y_CAP + 10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "05c_pvalue_vs_effectsize.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("[图] 05c_pvalue_vs_effectsize.png → p值-效应量散点图已保存")


# --- 图 5d：Top 数值特征箱线图 ---
if len(num_df) > 0:
    top_num = num_df.nsmallest(min(4, len(num_df)), 'P_Value')
    fig, axes = plt.subplots(1, len(top_num), figsize=(6 * len(top_num), 5))
    if len(top_num) == 1:
        axes = [axes]

    for ax, (_, row) in zip(axes, top_num.iterrows()):
        col = row['Feature']
        plot_data = df_model[[col, 'target']].dropna()
        if len(plot_data) > 50000:
            plot_data = plot_data.sample(50000, random_state=42)

        vivo_data = plot_data.loc[plot_data['target'] == 1, col]
        morto_data = plot_data.loc[plot_data['target'] == 0, col]

        bp = ax.boxplot([vivo_data.values, morto_data.values],   #ax.boxplot() 不支持 labels= 这个参数
                        patch_artist=True, widths=0.4)
        ax.set_xticklabels(['VIVO', 'MORTO'], fontsize=9)
        bp['boxes'][0].set_facecolor('#2ecc71')
        bp['boxes'][1].set_facecolor('#e74c3c')
        for w in bp['whiskers']:
            w.set_color('gray')
        for c in bp['caps']:
            c.set_color('gray')
        for m in bp['medians']:
            m.set_color('black')
            m.set_linewidth(2)

        ax.set_title(f'{col}\n(p={row["P_Value"]:.2e}, d={row["Effect_Size"]:.3f})',
                     fontsize=11, fontweight='bold')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    plt.suptitle('Top Discriminative Numerical Features by Target Group',
                 fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "05d_top_numerical_boxplots.png"), dpi=150, bbox_inches='tight')
    #plt.close()
    print("  [图] 05d_top_numerical_boxplots.png → 数值特征箱线图已保存")

# --- 图 5e：Top 分类特征堆叠柱状图 ---
if len(cat_df) > 0:
    top_cat = cat_df.nsmallest(min(4, len(cat_df)), 'P_Value')
    fig, axes = plt.subplots(1, len(top_cat), figsize=(5 * len(top_cat), 5))
    if len(top_cat) == 1:
        axes = [axes]

    for ax, (_, row) in zip(axes, top_cat.iterrows()):
        col = row['Feature']
        data = df_model[[col, 'target']].dropna()
        # 取 Top 8 类别
        top_categories = data[col].value_counts().head(8).index
        data_subset = data[data[col].isin(top_categories)]

        ct = pd.crosstab(data_subset[col], data_subset['target'], normalize='index')
        ct.columns = ['MORTO (Dead)', 'VIVO (Alive)']
        ct.sort_values('VIVO (Alive)', ascending=True, inplace=True)

        ct.plot(kind='barh', stacked=True, ax=ax,
                color=['#e74c3c', '#2ecc71'], edgecolor='white', width=0.7)
        ax.set_title(f'{col}\n(p={row["P_Value"]:.2e}, V={row["Cramér_V"]:.3f})',
                     fontsize=10, fontweight='bold')
        ax.set_xlabel('Proportion')
        ax.set_ylabel('')
        ax.legend(fontsize=7, loc='lower right')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # 在柱上标注存活率
        for i, (idx, r) in enumerate(ct.iterrows()):
            vivo_pct = r['VIVO (Alive)'] * 100
            if vivo_pct > 3:
                ax.text(r['MORTO (Dead)'] + r['VIVO (Alive)'] / 2, i,
                        f'{vivo_pct:.1f}%', ha='center', va='center',
                        fontsize=7, fontweight='bold', color='white')

    plt.suptitle('Top Discriminative Categorical Features: Survival Rate by Category',
                 fontsize=13, fontweight='bold', y=1.05)
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "05e_top_categorical_stackedbar.png"), dpi=150, bbox_inches='tight')
    plt.close()
    print("  [图] 05e_top_categorical_stackedbar.png → 分类特征堆叠柱状图")
