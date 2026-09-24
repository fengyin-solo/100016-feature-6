<template>
  <section class="page" data-module="excursion">
    <header class="page-head">
      <div>
        <h2>温度异常管理</h2>
        <p class="page-desc">按异常类型配置允许超限时长上限与最高温度上限：任一项越界即需处置，两项均达标才允许直接结单。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记温度异常事件</button>
        <button class="btn" type="button" @click="openRules">判定规则配置</button>
        <button class="btn" type="button" @click="exportRows">导出温度异常清单</button>
      </div>
    </header>

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
          <td v-for="column in columns" :key="column">
            <button v-if="column === '事件编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td>
            <span class="verdict-tag" :class="verdictClass(row.verdict)">{{ row.verdict }}</span>
            <span v-if="row.ruleInvalid" class="verdict-warn" :title="row.reasons">规则兜底</span>
          </td>
          <td class="row-actions">
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
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 事件详情：结论与列表共用同一后端口径 -->
    <div v-if="detailRow" class="modal-mask" @click.self="detailRow = null">
      <div class="modal">
        <div class="modal-head">
          <h3>温度异常事件详情</h3>
          <button class="btn ghost" type="button" @click="detailRow = null">关闭</button>
        </div>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detailRow[column] ?? '—' }}</dd>
          </template>
          <dt>当前状态</dt>
          <dd>{{ detailRow.status }}</dd>
        </dl>
        <div class="verdict-panel" :class="verdictClass(detailRow.verdict)">
          <div class="verdict-title">
            判定结论：<strong>{{ detailRow.verdict }}</strong>
            <span v-if="detailRow.snapshot" class="verdict-snapshot">结单时口径已冻结</span>
          </div>
          <p class="verdict-reason">{{ detailRow.reasons }}</p>
          <p class="verdict-source">依据规则：{{ detailRow.ruleSource }}<template v-if="detailRow.ruleInvalid">（规则缺失或无效，已沿用系统默认口径）</template></p>
        </div>
      </div>
    </div>

    <!-- 判定规则配置 -->
    <div v-if="rulesVisible" class="modal-mask" @click.self="closeRules">
      <div class="modal modal-wide">
        <div class="modal-head">
          <h3>超限判定规则配置</h3>
          <button class="btn ghost" type="button" @click="closeRules">关闭</button>
        </div>
        <p class="rules-tip">{{ defaultRuleText }}。规则缺失或填写无效的异常类型沿用该口径，并在列表中标注「规则兜底」。</p>
        <table class="data-table rules-table">
          <thead>
            <tr>
              <th>异常类型</th>
              <th>允许超限时长上限（分钟）</th>
              <th>允许最高温度上限（℃）</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in ruleRows" :key="rule.abnormalType || `new-${ruleRows.indexOf(rule)}`">
              <td>
                <input v-if="rule.editing" v-model="rule.abnormalType" placeholder="如：冷藏超限" />
                <span v-else>{{ rule.abnormalType }}</span>
              </td>
              <td><input v-model="rule.maxDuration" inputmode="decimal" placeholder="如：30" /></td>
              <td><input v-model="rule.maxTemperature" inputmode="decimal" placeholder="如：8" /></td>
              <td>
                <span v-if="rule.message" :class="rule.valid ? 'rule-ok' : 'rule-bad'">{{ rule.message }}</span>
              </td>
              <td class="row-actions">
                <button class="link" type="button" @click="saveRule(rule)">保存</button>
                <button v-if="rule.abnormalType && !rule.editing" class="link danger" type="button" @click="removeRule(rule)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn" type="button" @click="addRuleRow">新增异常类型规则</button>
        </div>
      </div>
    </div>

    <!-- 登记事件 -->
    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal">
        <div class="modal-head">
          <h3>登记温度异常事件</h3>
          <button class="btn ghost" type="button" @click="createVisible = false">关闭</button>
        </div>
        <form class="create-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="filter-item">
            <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span>
            <input v-model="createForm[field.key]" :placeholder="field.placeholder ?? ''" />
          </label>
          <div class="modal-actions">
            <button class="btn primary" type="submit">提交登记</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null> & {
  id: number
  verdict: string
  reasons: string
  ruleSource: string
  ruleInvalid: boolean
  snapshot: boolean
}

type RuleRow = {
  abnormalType: string
  maxDuration: string | number | null
  maxTemperature: string | number | null
  valid?: boolean
  message?: string
  editing?: boolean
}

const ENDPOINT = '/api/excursion'
const columns = ['事件编号', '关联运单', '异常类型', '超限时长', '最高温度', '发生时间', '处置人']
const actions = ['受理事件', '提交处置', '忽略事件']
const stats = [{ label: '待处置事件', value: 0 }, { label: '超限时长合计', value: 0 }, { label: '今日闭环数', value: 0 }]
const createFields: Array<{ key: string; label: string; required?: boolean; placeholder?: string }> = [
  { key: '事件编号', label: '事件编号', required: true },
  { key: '关联运单', label: '关联运单', required: true },
  { key: '异常类型', label: '异常类型', required: true, placeholder: '如：冷藏超限' },
  { key: '超限时长', label: '超限时长（分钟）' },
  { key: '最高温度', label: '最高温度（℃）' },
  { key: '发生时间', label: '发生时间' },
  { key: '处置人', label: '处置人' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const detailRow = ref<Row | null>(null)
const rulesVisible = ref(false)
const ruleRows = ref<RuleRow[]>([])
const defaultRuleText = ref('')
const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})

function verdictClass(verdict: string): string {
  if (verdict === '需要处置') return 'verdict-danger'
  if (verdict === '允许结单') return 'verdict-ok'
  return 'verdict-pending'
}

function flash(message: string, ok = false) {
  if (ok) {
    noticeMessage.value = message
    errorMessage.value = ''
  } else {
    errorMessage.value = message
    noticeMessage.value = ''
  }
}

type ActionResponse = { ok: boolean; message: string; entry?: Record<string, unknown> | null }

async function readResult(response: Response): Promise<ActionResponse> {
  try {
    return (await response.json()) as ActionResponse
  } catch {
    return { ok: response.ok, message: '温度异常操作未生效，请稍后重试' }
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createVisible.value = true
}

async function submitCreate() {
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const result = await readResult(response)
    if (!result.ok) {
      flash(result.message)
      return
    }
    createVisible.value = false
    flash(result.message, true)
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '温度异常登记失败')
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('温度异常事件详情读取失败')
    }
    detailRow.value = (await response.json()) as Row
  } catch (error) {
    flash(error instanceof Error ? error.message : '温度异常详情读取失败')
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const result = await readResult(response)
    if (!result.ok) {
      // 例如结单时被新口径拦下：把后端给出的越界原因直接展示出来
      flash(result.message)
      return
    }
    flash(result.message, true)
    if (detailRow.value && detailRow.value.id === row.id) {
      detailRow.value = null
    }
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '温度异常操作失败')
  }
}

async function openRules() {
  rulesVisible.value = true
  await loadRules()
}

function closeRules() {
  rulesVisible.value = false
}

function addRuleRow() {
  ruleRows.value.push({ abnormalType: '', maxDuration: '', maxTemperature: '', editing: true })
}

async function loadRules() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/rules`)
    if (!response.ok) {
      throw new Error('判定规则读取失败')
    }
    const payload = (await response.json()) as { defaultRule: string; items: RuleRow[] }
    defaultRuleText.value = payload.defaultRule
    ruleRows.value = payload.items.map((item) => ({ ...item, editing: false }))
  } catch (error) {
    flash(error instanceof Error ? error.message : '判定规则读取失败')
  }
}

async function saveRule(rule: RuleRow) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/rules`, {
      method: 'PUT',
      body: JSON.stringify({
        abnormalType: rule.abnormalType,
        maxDuration: rule.maxDuration === '' ? null : rule.maxDuration,
        maxTemperature: rule.maxTemperature === '' ? null : rule.maxTemperature,
      }),
    })
    const result = await readResult(response)
    if (!result.ok) {
      rule.message = result.message
      rule.valid = false
      flash(result.message)
      return
    }
    const saved = result.entry as RuleRow & { rechecked?: { affected: number; verdictChanged: number } }
    rule.abnormalType = saved.abnormalType
    rule.maxDuration = saved.maxDuration
    rule.maxTemperature = saved.maxTemperature
    rule.valid = saved.valid
    rule.message = saved.message
    rule.editing = false
    const changed = saved.rechecked?.verdictChanged ?? 0
    flash(`${result.message}，其中 ${changed} 条处置中事件结论发生变化`, true)
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '判定规则保存失败')
  }
}

async function removeRule(rule: RuleRow) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/rules/${encodeURIComponent(rule.abnormalType)}`, {
      method: 'DELETE',
    })
    const result = await readResult(response)
    if (!result.ok) {
      flash(result.message)
      return
    }
    flash(result.message, true)
    await loadRules()
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '判定规则删除失败')
  }
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
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    flash(error instanceof Error ? error.message : '温度异常列表读取失败')
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
}
.verdict-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid transparent;
}
.verdict-danger {
  color: #b42318;
  background: #fee4e2;
  border-color: #fda29b;
}
.verdict-ok {
  color: #067647;
  background: #dcfae6;
  border-color: #7ce2b0;
}
.verdict-pending {
  color: #b54708;
  background: #fef0c7;
  border-color: #fedf89;
}
.verdict-warn {
  margin-left: 6px;
  font-size: 12px;
  color: #b54708;
}
.notice-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 560px;
  max-height: 82vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
}
.modal-wide {
  width: 820px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.modal-head h3 {
  margin: 0;
  font-size: 16px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 6px 12px;
  margin: 0 0 14px;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.verdict-panel {
  border-radius: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
}
.verdict-panel.verdict-danger {
  background: #fef3f2;
}
.verdict-panel.verdict-ok {
  background: #f3fef7;
}
.verdict-panel.verdict-pending {
  background: #fffaeb;
}
.verdict-title {
  font-size: 14px;
}
.verdict-snapshot {
  margin-left: 8px;
  font-size: 12px;
  color: var(--muted);
}
.verdict-reason {
  margin: 6px 0 4px;
  font-size: 13px;
}
.verdict-source {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.rules-tip {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 10px;
}
.rules-table input {
  width: 100%;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.rule-ok {
  color: #067647;
  font-size: 12px;
}
.rule-bad {
  color: #b42318;
  font-size: 12px;
}
.link.danger {
  color: #b42318;
}
.modal-actions {
  margin-top: 12px;
  text-align: right;
}
.create-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.create-form .filter-item input {
  width: 100%;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
}
</style>
