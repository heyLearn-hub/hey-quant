REPORT_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <style>
    :root { color-scheme: light; --ink:#17202a; --muted:#5f6b7a; --line:#d9e0e8; --bg:#f6f8fb; --panel:#fff; --accent:#0f766e; --warn:#b45309; --bad:#b91c1c; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }
    header { padding:28px 32px 18px; background:#fff; border-bottom:1px solid var(--line); }
    h1 { margin:0 0 8px; font-size:28px; letter-spacing:0; }
    h2 { margin:26px 0 12px; font-size:20px; }
    main { max-width:1280px; margin:0 auto; padding:24px 28px 40px; }
    .meta { color:var(--muted); font-size:14px; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; }
    .tile, section { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }
    .tile b { display:block; font-size:22px; margin-top:6px; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:#334155; background:#f8fafc; font-weight:650; }
    .tag { display:inline-block; border-radius:999px; padding:3px 8px; font-size:12px; font-weight:650; }
    .buy { background:#d1fae5; color:#065f46; }
    .watch { background:#e0f2fe; color:#075985; }
    .trim { background:#fef3c7; color:#92400e; }
    .exit { background:#fee2e2; color:#991b1b; }
    .muted { color:var(--muted); }
    .issues li { margin:4px 0; }
    @media (max-width: 900px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } main { padding:16px; } table { font-size:13px; } }
  </style>
</head>
<body>
  <header>
    <h1>{{ title }}</h1>
    <div class="meta">As of {{ as_of }} · 本地研究提醒系统 · 不自动下单</div>
  </header>
  <main>
    <div class="grid">
      <div class="tile">扫描股票数 <b>{{ summary.ticker_count }}</b></div>
      <div class="tile">核心候选 <b>{{ summary.core_count }}</b></div>
      <div class="tile">减仓/退出候选 <b>{{ summary.risk_count }}</b></div>
      <div class="tile">LOTS 偏离 <b>{{ summary.position_drift_count }}</b></div>
    </div>

    <section>
      <h2>核心 1-2 个持仓候选</h2>
      <table>
        <thead><tr><th>Ticker</th><th>动作</th><th>综合分</th><th>技术分</th><th>质量分</th><th>初始股数</th><th>目标股数</th><th>止损参考</th><th>质量说明</th></tr></thead>
        <tbody>
          {% for row in core_signals %}{% set s = row.signal %}
          <tr>
            <td><b>{{ s.ticker }}</b></td>
            <td><span class="tag {{ row.css }}">{{ s.action }}</span></td>
            <td>{{ "%.1f"|format(s.score) }}</td>
            <td>{{ "%.1f"|format(s.technical_score) }}</td>
            <td>{{ "%.1f"|format(s.quality.score) }}</td>
            <td>{{ "%.0f"|format(s.position.initial_shares) }}</td>
            <td>{{ "%.0f"|format(s.position.target_shares) }}</td>
            <td>{{ "%.2f"|format(s.position.stop_price) }}</td>
            <td>{{ s.quality.note }}</td>
          </tr>
          {% else %}
          <tr><td colspan="9" class="muted">暂无同时通过量化门槛和 Supervisor 审查的核心候选；保持观察或等待更明确趋势。</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>GPT / Supervisor 最终审查</h2>
      <table>
        <thead><tr><th>Ticker</th><th>审查结果</th><th>最终动作</th><th>审批分</th><th>审查方</th><th>理由</th><th>阻断项</th><th>执行前检查</th></tr></thead>
        <tbody>
          {% for r in supervisor_reviews %}
          <tr>
            <td><b>{{ r.ticker }}</b></td>
            <td>{{ r.decision }}</td>
            <td>{{ r.final_action }}</td>
            <td>{{ "%.1f"|format(r.approval_score) }}</td>
            <td>{{ r.provider }}</td>
            <td>{{ r.rationale }}</td>
            <td>{{ "; ".join(r.blockers) if r.blockers else "无" }}</td>
            <td>{{ "; ".join(r.required_checks) }}</td>
          </tr>
          {% else %}
          <tr><td colspan="8" class="muted">Supervisor 审查未启用。</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>真实仓位 vs LOTS</h2>
      <table>
        <thead><tr><th>Ticker</th><th>结论</th><th>实际股数</th><th>LOTS 初始</th><th>LOTS 目标</th><th>实际仓位</th><th>目标仓位</th><th>股数偏离</th><th>止损风险/NAV</th><th>风险预算</th><th>说明</th></tr></thead>
        <tbody>
          {% for row in drift_reviews %}{% set d = row.review %}
          <tr>
            <td><b>{{ d.ticker }}</b></td>
            <td><span class="tag {{ row.css }}">{{ d.action }}</span></td>
            <td>{{ "%.2f"|format(d.actual_shares) }}</td>
            <td>{{ "%.0f"|format(d.lots_initial_shares) if d.lots_initial_shares is not none else "无信号" }}</td>
            <td>{{ "%.0f"|format(d.lots_target_shares) if d.lots_target_shares is not none else "无信号" }}</td>
            <td>{{ "%.1f%%"|format(d.actual_weight * 100) if d.actual_weight is not none else "无数据" }}</td>
            <td>{{ "%.1f%%"|format(d.target_weight * 100) if d.target_weight is not none else "无信号" }}</td>
            <td>{{ "%.1f%%"|format(d.drift_pct * 100) if d.drift_pct is not none else "无信号" }}</td>
            <td>{{ "%.1f%%"|format(d.stop_loss_nav_pct * 100) if d.stop_loss_nav_pct is not none else "无法计算" }}</td>
            <td>{{ "%.1f%%"|format(d.risk_budget_pct * 100) if d.risk_budget_pct is not none else "无信号" }}</td>
            <td>{{ "; ".join(d.notes) }}</td>
          </tr>
          {% else %}
          <tr><td colspan="11" class="muted">还没有录入持仓，暂不检查真实仓位和 LOTS 的偏离。</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>利润保护与退出规则</h2>
      <table>
        <thead><tr><th>Ticker</th><th>保护动作</th><th>当前价</th><th>成本</th><th>当前浮盈</th><th>最高浮盈</th><th>利润回吐</th><th>动态保护线</th><th>说明</th></tr></thead>
        <tbody>
          {% for row in exit_reviews %}{% set r = row.review %}
          <tr>
            <td><b>{{ r.ticker }}</b></td>
            <td><span class="tag {{ row.css }}">{{ r.action }}</span></td>
            <td>{{ "%.2f"|format(r.close) if r.close is not none else "无数据" }}</td>
            <td>{{ "%.2f"|format(r.average_cost) }}</td>
            <td>{{ "%.1f%%"|format(r.current_pnl_pct * 100) if r.current_pnl_pct is not none else "无数据" }}</td>
            <td>{{ "%.1f%%"|format(r.highest_pnl_pct * 100) if r.highest_pnl_pct is not none else "无数据" }}</td>
            <td>{{ "%.1f%%"|format(r.profit_giveback_pct * 100) if r.profit_giveback_pct is not none else "未进入盈利保护" }}</td>
            <td>{{ "%.2f"|format(r.dynamic_stop) if r.dynamic_stop is not none else "未设置" }}</td>
            <td>{{ "; ".join(r.notes) }}</td>
          </tr>
          {% else %}
          <tr><td colspan="9" class="muted">还没有录入持仓，暂不生成利润保护规则。</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>当前持仓检查</h2>
      <table>
        <thead><tr><th>Ticker</th><th>股数</th><th>成本</th><th>系统价格</th><th>浮盈亏</th><th>系统动作</th><th>保护动作</th><th>止损参考</th><th>备注</th></tr></thead>
        <tbody>
          {% for p in positions %}{% set s = signal_by_ticker.get(p.ticker) %}
          {% set er = exit_review_by_ticker.get(p.ticker) %}
          {% set dr = drift_review_by_ticker.get(p.ticker) %}
          <tr>
            <td><b>{{ p.ticker }}</b></td>
            <td>{{ "%.2f"|format(p.shares) }}</td>
            <td>{{ "%.2f"|format(p.average_cost) }}</td>
            <td>{{ "%.2f"|format(s.close) if s else "无数据" }}</td>
            <td>{% if s %}{{ "%.1f%%"|format((s.close / p.average_cost - 1) * 100) }}{% else %}无数据{% endif %}</td>
            <td>{{ s.action if s else "无信号" }}</td>
            <td>{{ dr.action if dr else er.action if er else "未生成" }}</td>
            <td>{% if s %}{{ "%.2f"|format(s.position.stop_price) }}{% elif p.current_stop %}{{ "%.2f"|format(p.current_stop) }}{% else %}未设置{% endif %}</td>
            <td>{{ p.thesis_note }}</td>
          </tr>
          {% else %}
          <tr><td colspan="9" class="muted">还没有录入持仓。可以在本地网页服务里新增持仓。</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>完整观察池与 LOTS 仓位</h2>
      <table>
        <thead><tr><th>Ticker</th><th>动作</th><th>综合分</th><th>技术分</th><th>质量分</th><th>价格</th><th>初始股数</th><th>目标股数</th><th>止损参考</th><th>约束</th><th>风控说明</th></tr></thead>
        <tbody>
          {% for row in signals %}{% set s = row.signal %}
          <tr>
            <td><b>{{ s.ticker }}</b></td>
            <td><span class="tag {{ row.css }}">{{ s.action }}</span></td>
            <td>{{ "%.1f"|format(s.score) }}</td>
            <td>{{ "%.1f"|format(s.technical_score) }}</td>
            <td>{{ "%.1f"|format(s.quality.score) }}</td>
            <td>{{ "%.2f"|format(s.close) }}</td>
            <td>{{ "%.0f"|format(s.position.initial_shares) }}</td>
            <td>{{ "%.0f"|format(s.position.target_shares) }}</td>
            <td>{{ "%.2f"|format(s.position.stop_price) }}</td>
            <td>{{ s.position.binding_constraint }}</td>
            <td>{{ "; ".join(s.risk.notes) }}{% if review_by_ticker.get(s.ticker) %}; Supervisor: {{ review_by_ticker[s.ticker].final_action }}{% endif %}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Public Equity 风险解释字段</h2>
      <table>
        <thead><tr><th>Ticker</th><th>Intended Alpha</th><th>Unwanted Risk</th><th>Retained Exposure</th><th>Liquidity / Exit Posture</th></tr></thead>
        <tbody>
          {% for row in signals[:10] %}{% set s = row.signal %}
          <tr><td><b>{{ s.ticker }}</b></td><td>{{ s.position.intended_alpha }}</td><td>{{ s.position.unwanted_risk }}</td><td>{{ s.position.retained_exposure }}</td><td>{{ s.position.liquidity_exit_posture }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>回测摘要</h2>
      <table>
        <thead><tr><th>策略</th><th>年化</th><th>最大回撤</th><th>Sharpe</th><th>胜率</th><th>盈亏比</th><th>换手</th><th>平均持仓天数</th><th>相对基准超额</th></tr></thead>
        <tbody>
          {% for m in metrics %}
          <tr>
            <td>{{ m.strategy }}</td>
            <td>{{ "%.1f%%"|format(m.annual_return * 100) }}</td>
            <td>{{ "%.1f%%"|format(m.max_drawdown * 100) }}</td>
            <td>{{ "%.2f"|format(m.sharpe) }}</td>
            <td>{{ "%.1f%%"|format(m.win_rate * 100) }}</td>
            <td>{{ "%.2f"|format(m.profit_factor) }}</td>
            <td>{{ "%.1fx"|format(m.turnover) }}</td>
            <td>{{ "%.0f"|format(m.avg_holding_days) }}</td>
            <td>{{ "%.1f%%"|format(m.benchmark_excess_return * 100) }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Serenity Alpha 研究增强层</h2>
      <p class="muted">当前版本保留新闻/产业需求输入接口：新闻不会自动替代量化信号，只能把“已发生的需求变化 -> 财务传导 -> 验证指标 -> 仓位条件”写入后续研究记录。</p>
    </section>

    {% if issues %}
    <section>
      <h2>数据质量提示</h2>
      <ul class="issues">
        {% for issue in issues %}<li><b>{{ issue.ticker }}</b> · {{ issue.provider }} · {{ issue.message }}</li>{% endfor %}
      </ul>
    </section>
    {% endif %}
  </main>
</body>
</html>
"""
