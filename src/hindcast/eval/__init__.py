"""hindcast.eval —— 诚实评估量具（红队 2026-05-16 R3–R6 + §1 Layer2 的标准方法）。

**隔离模块**：只依赖 numpy/scipy；**不 import hindcast 任何核心/数据模块**，
不碰 `kaofa_f.py / continuous.py / school_ledger.py / fred.py`（RAG 正在 #2 改动的文件），
零文件撞车；**不读 /state/asof 或任何被冻结的数据通道，不产任何可计数结果**——
它只是"量具"，在合成数据上自验，等 #2 交出干净数据后直接用对的尺重做预注册一轮。

为何用 numpy/scipy 正确实现而非 arch/statsmodels/sklearn：项目 .venv 为 py3.14 极简环境，
重 C 扩展库无可靠 3.14 轮子（源码编译易失败/极慢）。红队的**实质**是"用正确的标准方法、
别手搓错的"——标准方法在 numpy/scipy 上 10–40 行即可正确实现且可审计；接口与重库一致，
将来重库可达时替换为一行 import 即可。substance 不打折，依赖风险归零。
"""

from hindcast.eval.metrics import (  # noqa: F401
    amplitude_vs_null,
    clark_west,
    diebold_mariano,
    hac_mean_tstat,
    log_loss,
    moving_block_bootstrap_ci,
    one_sided_hp_credit_gap,
    pesaran_timmermann,
    pr_auc,
    reliability_bins,
    brier,
    brier_skill_score,
)
