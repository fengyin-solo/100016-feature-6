<template>
  <section class="page" data-module="excursion">
    <header class="page-head">
      <div>
        <h2>温度异常管理</h2>
        <p class="page-desc">
          按异常类型配置超限时长上限与最高温度上限：任意一项越界判为需要处置，两项达标才允许直接结单；
          规则刷新后处置中的事件重新进入即按新口径再评估。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记温度异常事件</button>
        <button class="btn" type="button" :class="{ ghost: showRules }" @click="showRules = !showRules">
          {{ showRules ? '收起判定规则' : '配置判定规则' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出温度异常清单</button>
      </div>
    </header>

    <section v-if="showRules" class="rule-panel">
      <div class="rule-head">
        <h3>超限判定规则</h3>
        <p class="page-desc">
          按异常类型分别设定允许的超限时长上限（分钟）与最高温度上限（℃）。
          规则缺失或填写无效时会说明原因，并保留原有判定。
        </p>
      </div>
      <table class="data-table rule-table">
        <thead>
          <tr>
            <th>异常类型</th>
            <th>超限时长上限（分钟）</th>
            <th>最高温度上限（℃）</th>
            <th>配置状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rule in ruleDrafts" :key="rule.key" :class="{ 'rule-invalid': ruleErrors[rule.key] }">
            <td>
              <input
                v-if="rule.isNew"
                v-model="rule.abnormalType"
                placeholder="输入异常类型，如：高温超限"
              />
              <span v-else>{{ rule.abnormalType }}</span>
            </td>
            <td><input v-model.number="rule.durationLimit" type="number" min="0" step="1" placeholder="如：30" /></td>
            <td><input v-model.number="rule.tempLimit" type="number" min="0" step="0.1" placeholder="如：8" /></td>
            <td>
              <span v-if="ruleErrors[rule.key]" class="tag tag-fallback">未生效</span>
              <span v-else-if="rule.isNew" class="tag tag-fallback">新增</span>
              <span v-else class="tag tag-close">已配置</span>
            </td>
            <td>
              <button class="link" type="button" @click="saveRule(rule)">保存</button>
              <button v-if="rule.isNew" class="link btn-danger" type="button" @click="removeDraft(rule)">移除</button>
            </td>
          </tr>
          <tr v-if="!ruleDrafts.length">
            <td colspan="5" class="empty-state">暂无判定规则，先新增一条异常类型的判定口径</td>
          </tr>
        </tbody>
      </table>
      <div class="rule-foot">
        <button class="btn" type="button" @click="addRuleDraft">新增异常类型规则</button>
        <button class="btn ghost" type="button" @click="reloadRules">放弃未保存的修改</button>
        <span v-if="ruleMessage" class="rule-message">{{ ruleMessage }}</span>
      </div>
    </section>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>判定结论</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span class="tag" :class="conclusionClass(String(row['判定结论']))">
              {{ row['判定结论'] ?? '—' }}
            </span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无温度异常数据，可先登记温度异常事件</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条温度异常记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="drawer-mask" @click.self="closeDetail">
      <aside class="drawer">
        <header class="drawer-head">
          <h3>温度异常事件详情</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-list">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
          <dt>判定结论</dt>
          <dd>
            <span class="tag" :class="conclusionClass(String(detail['判定结论']))">
              {{ detail['判定结论'] ?? '—' }}
            </span>
          </dd>
          <dt>规则状态</dt>
          <dd>{{ detail['规则状态'] ?? '—' }}</dd>
          <dt>判定依据</dt>
          <dd class="detail-reason">{{ detail['判定依据'] ?? '—' }}</dd>
          <dt>当前状态</dt>
          <dd>{{ detail.status ?? '—' }}</dd>
        </dl>
        <div class="drawer-actions">
          <button
            v-for="action in actions"
            :key="action"
            class="btn"
            type="button"
            @click="runAction(action, detail)"
          >
            {{ action }}
          </button>
        </div>
        <p v-if="detailMessage" class="detail-message">{{ detailMessage }}</p>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface RuleDraft {
  key: string
  abnormalType: string
  durationLimit: number | null
  tempLimit: number | null
  isNew: boolean
}

const ENDPOINT = '/api/excursion'
const columns = ["事件编号", "关联运单", "异常类型", "超限时长", "最高温度", "发生时间", "处置人"]
const detailFields = columns
const actions = ["受理事件", "提交处置", "忽略事件"]
const stats = [{"label": "待处置事件", "value": 0}, {"label": "超限时长合计", "value": 0}, {"label": "今日闭环数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const showRules = ref(false)
const ruleDrafts = ref<RuleDraft[]>([])
const ruleErrors = ref<Record<string, string>>({})
const ruleMessage = ref('')
let ruleDraftSeq = 0

const detail = ref<Row | null>(null)
const detailMessage = ref('')

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '温度异常事件登记入口尚未接入审批流'
}

function conclusionClass(conclusion: string) {
  if (conclusion === '需要处置') return 'tag-handle'
  if (conclusion === '允许直接结单') return 'tag-close'
  return 'tag-fallback'
}

// ---------- 判定规则 ----------
async function reloadRules() {
  ruleMessage.value = ''
  ruleErrors.value = {}
  try {
    const response = await request(`${ENDPOINT}/rules`)
    if (!response.ok) {
      throw new Error('判定规则读取失败')
    }
    const payload = await response.json()
    ruleDrafts.value = (payload.items ?? []).map((item: Row) => ({
      key: `saved-${String(item['异常类型'])}`,
      abnormalType: String(item['异常类型'] ?? ''),
      durationLimit: item['超限时长上限'] === null || item['超限时长上限'] === undefined
        ? null
        : Number(item['超限时长上限']),
      tempLimit: item['最高温度上限'] === null || item['最高温度上限'] === undefined
        ? null
        : Number(item['最高温度上限']),
      isNew: false,
    }))
  } catch (error) {
    ruleMessage.value = error instanceof Error ? error.message : '判定规则读取失败'
  }
}

function addRuleDraft() {
  ruleDrafts.value.push({
    key: `new-${ruleDraftSeq++}`,
    abnormalType: '',
    durationLimit: null,
    tempLimit: null,
    isNew: true,
  })
}

function removeDraft(draft: RuleDraft) {
  ruleDrafts.value = ruleDrafts.value.filter(item => item.key !== draft.key)
  delete ruleErrors.value[draft.key]
}

async function saveRule(draft: RuleDraft) {
  ruleMessage.value = ''
  const abnormalType = draft.abnormalType.trim()
  if (!abnormalType) {
    ruleErrors.value[draft.key] = '异常类型不能为空'
    return
  }
  if (draft.durationLimit === null || !Number.isFinite(draft.durationLimit) || draft.durationLimit < 0
    || draft.tempLimit === null || !Number.isFinite(draft.tempLimit) || draft.tempLimit < 0) {
    ruleErrors.value[draft.key] = '两项上限均需填写为不小于 0 的数字'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/rules/${encodeURIComponent(abnormalType)}`, {
      method: 'PUT',
      body: JSON.stringify({
        values: { 超限时长上限: draft.durationLimit, 最高温度上限: draft.tempLimit },
      }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload || payload.ok === false) {
      ruleErrors.value[draft.key] = payload?.message || '规则保存失败'
      ruleMessage.value = ''
      return
    }
    delete ruleErrors.value[draft.key]
    ruleMessage.value = payload.message || '判定规则已刷新'
    await reloadRules()
    // 口径调整刷新后，列表与详情中的处置中事件按新规则再评估
    await reload()
    if (detail.value) {
      await openDetail(detail.value)
    }
  } catch (error) {
    ruleErrors.value[draft.key] = error instanceof Error ? error.message : '规则保存失败'
  }
}

// ---------- 事件动作与详情 ----------
async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  detailMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null) as
      { ok?: boolean; message?: string; entry?: Row | null } | null
    if (!response.ok || !payload) {
      throw new Error('温度异常动作未生效，请稍后重试')
    }
    if (payload.ok === false) {
      // 结单卡口、非法动作等：直接展示后端说明的原因
      errorMessage.value = payload.message || '温度异常动作未生效'
      detailMessage.value = errorMessage.value
      return
    }
    if (detail.value && Number(detail.value.id) === Number(row.id) && payload.entry) {
      detail.value = payload.entry
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温度异常操作失败'
  }
}

async function openDetail(row: Row) {
  detailMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('温度异常详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    detail.value = { ...row }
    detailMessage.value = error instanceof Error ? error.message : '温度异常详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
  detailMessage.value = ''
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('温度异常事件列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '温度异常列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadRules()
})
</script>

<style scoped>
.rule-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.rule-head h3 { margin: 0 0 4px; font-size: 15px; }
.rule-table { margin-top: 8px; }
.rule-table input {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
}
.rule-invalid td { background: #fef3f2; }
.rule-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.rule-message { font-size: 12px; color: var(--muted); }
.btn-danger { color: #b42318; margin-left: 8px; }

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}
.tag-handle { background: #fef3f2; color: #b42318; border: 1px solid #fda29b; }
.tag-close { background: #ecfdf3; color: #027a48; border: 1px solid #73e2a3; }
.tag-fallback { background: #f2f4f7; color: #475467; border: 1px solid #d0d5dd; }

.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  justify-content: flex-end;
  z-index: 1000;
}
.drawer {
  width: 460px;
  max-width: 92vw;
  height: 100%;
  background: #fff;
  padding: 18px 20px;
  overflow-y: auto;
  box-shadow: -8px 0 24px rgba(16, 24, 40, 0.12);
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.drawer-head h3 { margin: 0; font-size: 16px; }
.detail-list {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 8px 12px;
  margin: 0 0 16px;
  font-size: 13px;
}
.detail-list dt { color: var(--muted); }
.detail-list dd { margin: 0; }
.detail-reason { color: #344054; }
.drawer-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.detail-message { margin-top: 12px; font-size: 12px; color: #b42318; }
</style>
