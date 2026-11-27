// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { h, nextTick, reactive, type SetupContext, type VNodeChild } from 'vue'

import { ApiRequestError, wasShown } from '@/api/errors'
import type { ThinktankDictItem, ThinktankDictSlug } from '@/api/codebook'
import { useAuthStore } from '@/stores/auth'
import ThinktankDictList from './ThinktankDictList.vue'

const mocks = vi.hoisted(() => ({
  route: null as { path: string; query: Record<string, unknown>; meta: Record<string, unknown> } | null,
  replace: vi.fn(),
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  importFile: vi.fn(),
  downloadFile: vi.fn(),
  fetchFilterOptions: vi.fn(),
  searchFilterOptions: vi.fn(),
  runExcelImport: vi.fn(),
  reportImportResult: vi.fn(),
  msgSuccess: vi.fn(),
  msgError: vi.fn(),
  confirm: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
  onBeforeRouteLeave: () => undefined,
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.msgSuccess, error: mocks.msgError },
  ElMessageBox: { confirm: mocks.confirm },
}))

vi.mock('@/api/codebook', () => ({
  listThinktankDicts: mocks.list,
  createThinktankDict: mocks.create,
  updateThinktankDict: mocks.update,
  deleteThinktankDict: mocks.remove,
  importThinktankDicts: mocks.importFile,
}))

vi.mock('@/api/download', () => ({
  downloadFile: mocks.downloadFile,
}))

vi.mock('@/api/filterOptions', () => ({
  fetchFilterOptions: mocks.fetchFilterOptions,
  searchFilterOptions: mocks.searchFilterOptions,
}))

vi.mock('@/api/excelImport', () => ({
  runExcelImport: mocks.runExcelImport,
  reportImportResult: mocks.reportImportResult,
  importUi: { visible: false },
}))

function makeItem(overrides: Partial<ThinktankDictItem> = {}): ThinktankDictItem {
  return {
    id: 'dict-1',
    dict_type: 'file_types',
    name: '经分',
    sort_order: 1,
    version: 2,
    created_at: '2026-11-26 10:00:00',
    created_by_name: '管理员',
    updated_at: '2026-11-26 12:30:00',
    updated_by_name: '张三',
    ...overrides,
  }
}

function cellText(row: ThinktankDictItem, prop?: string): string {
  if (!prop) return ''
  const raw = (row as unknown as Record<string, unknown>)[prop]
  return typeof raw === 'string' || typeof raw === 'number' ? String(raw) : ''
}

type Emitter = { $emit: (event: string, ...args: unknown[]) => void }
const fire = (found: { vm: unknown }, event: string, ...args: unknown[]) => (found.vm as Emitter).$emit(event, ...args)

const STUBS = {
  ListPage: {
    name: 'ListPage',
    props: ['title', 'hint', 'total', 'page', 'pageSize', 'loading', 'error'],
    emits: ['retry', 'update:page', 'update:pageSize', 'change'],
    setup(props: { title?: string; hint?: string }, { slots }: SetupContext) {
      return () =>
        h('section', { class: 'list-page-stub' }, [
          h('h1', { class: 'page-title' }, props.title ?? ''),
          h('p', { class: 'page-hint' }, props.hint ?? ''),
          h('div', { class: 'page-actions' }, slots.actions?.()),
          h('div', { class: 'page-filters' }, slots.filters?.()),
          h('div', { class: 'page-body' }, slots.default?.()),
        ])
    },
  },
  FilterBar: {
    name: 'FilterBar',
    props: ['query', 'applied'],
    emits: ['search', 'reset'],
    setup(_props: Record<string, unknown>, { slots, emit }: SetupContext) {
      return () =>
        h('form', { class: 'filter-bar-stub' }, [
          slots.default?.(),
          h('button', { type: 'button', class: 'btn-search', onClick: () => emit('search') }, '查询'),
          h('button', { type: 'button', class: 'btn-reset', onClick: () => emit('reset') }, '重置'),
        ])
    },
  },
  FilterSelect: {
    name: 'FilterSelect',
    props: ['modelValue', 'options', 'placeholder'],
    emits: ['update:modelValue'],
    setup(props: { options?: unknown[]; placeholder?: string }) {
      return () =>
        h('div', { class: 'filter-select-stub', 'data-placeholder': props.placeholder ?? '' }, String(props.options?.length ?? 0))
    },
  },
  ImportButton: {
    name: 'ImportButton',
    props: ['hint', 'upload'],
    setup(props: { hint?: string }) {
      return () => h('button', { type: 'button', class: 'import-btn-stub', title: props.hint ?? '' }, '导入')
    },
  },
  ExportButton: {
    name: 'ExportButton',
    props: ['allowed', 'loading'],
    emits: ['click'],
    setup(props: { allowed?: boolean; loading?: boolean }, { emit }: SetupContext) {
      return () =>
        h('button', {
          type: 'button',
          class: 'export-btn-stub',
          disabled: !props.allowed || Boolean(props.loading),
          onClick: () => emit('click'),
        }, '导出')
    },
  },
  AuditLogButton: {
    name: 'AuditLogButton',
    props: ['module'],
    setup(props: { module?: string }) {
      return () => h('button', { type: 'button', class: 'audit-btn-stub', 'data-module': props.module ?? '' }, '操作记录')
    },
  },
  TableSkeleton: {
    name: 'TableSkeleton',
    props: ['columns', 'hasActions'],
    template: '<div class="table-skeleton-stub">loading</div>',
  },
  ListEmpty: true,
  'el-table': {
    name: 'ElTable',
    props: ['data'],
    setup(props: { data?: ThinktankDictItem[] }, { slots }: SetupContext) {
      return () => {
        const rows = props.data ?? []
        const colVNodes = slots.default?.() ?? []
        return h('div', { class: 'el-table-stub' }, [
          rows.length === 0
            ? slots.empty?.()
            : rows.map((row) =>
                h(
                  'div',
                  { class: 'table-row', key: row.id },
                  colVNodes.map((vnode) => {
                    const colProps = (vnode.props ?? {}) as { label?: string; prop?: string }
                    const colSlots = vnode.children as { default?: (arg: { row: ThinktankDictItem }) => VNodeChild } | null
                    if (!colProps.label) return null
                    return h('div', { class: 'table-cell', 'data-label': colProps.label }, [
                      colSlots?.default ? colSlots.default({ row }) : cellText(row, colProps.prop),
                    ])
                  }),
                ),
              ),
        ])
      }
    },
  },
  'el-table-column': {
    name: 'ElTableColumn',
    props: ['label', 'prop', 'className'],
    setup() {
      return () => null
    },
  },
  'el-dialog': {
    name: 'ElDialog',
    props: ['modelValue', 'title', 'closeOnClickModal', 'closeOnPressEscape', 'showClose', 'beforeClose'],
    emits: ['update:modelValue'],
    setup(
      props: {
        modelValue?: boolean
        title?: string
        closeOnClickModal?: boolean
        closeOnPressEscape?: boolean
        showClose?: boolean
      },
      { slots }: SetupContext,
    ) {
      return () =>
        props.modelValue
          ? h(
              'div',
              {
                class: 'el-dialog-stub',
                'data-close-modal': String(props.closeOnClickModal ?? true),
                'data-close-escape': String(props.closeOnPressEscape ?? true),
                'data-show-close': String(props.showClose ?? true),
              },
              [
                h('div', { class: 'dialog-title' }, props.title ?? ''),
                h('div', { class: 'dialog-body' }, slots.default?.()),
                h('div', { class: 'dialog-footer' }, slots.footer?.()),
              ],
            )
          : null
    },
  },
  'el-form': {
    name: 'ElForm',
    props: ['disabled'],
    template: '<form class="el-form-stub"><slot /></form>',
  },
  'el-form-item': {
    name: 'ElFormItem',
    props: ['label', 'error'],
    setup(props: { label?: string }, { slots }: SetupContext) {
      return () =>
        h('div', { class: 'el-form-item-stub', 'data-label': props.label ?? '' }, [
          h('label', props.label ?? ''),
          slots.default?.(),
          slots.error?.(),
        ])
    },
  },
  'el-input': {
    name: 'ElInput',
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue'],
    setup(props: { modelValue?: string; placeholder?: string }, { emit }: SetupContext) {
      return () =>
        h('input', {
          class: 'el-input-stub',
          value: props.modelValue ?? '',
          placeholder: props.placeholder ?? '',
          onInput: (e: Event) => emit('update:modelValue', (e.target as HTMLInputElement).value),
        })
    },
  },
  'el-button': {
    name: 'ElButton',
    props: ['disabled', 'loading', 'type'],
    emits: ['click'],
    setup(props: { disabled?: boolean; loading?: boolean; type?: string }, { slots, emit }: SetupContext) {
      return () =>
        h(
          'button',
          {
            type: 'button',
            class: `el-button-stub ${props.type ? `el-button--${props.type}` : ''}`.trim(),
            disabled: Boolean(props.disabled) || Boolean(props.loading),
            onClick: () => emit('click'),
          },
          slots.default?.(),
        )
    },
  },
  'el-alert': {
    name: 'ElAlert',
    props: ['title'],
    setup(props: { title?: string }) {
      return () => h('div', { class: 'el-alert-stub', role: 'alert' }, props.title ?? '')
    },
  },
}

function grantPermissions(entries: { code: string; level: 'READ' | 'EXPORT' | 'FULL' }[]) {
  const auth = useAuthStore()
  auth.resources = entries
}

function mountPage(options: {
  slug?: ThinktankDictSlug
  metaSlug?: string
  path?: string
  query?: Record<string, unknown>
} = {}) {
  mocks.route = reactive({
    path: options.path ?? `/codebook/thinktank/${options.slug ?? options.metaSlug ?? 'file-types'}`,
    query: options.query ?? {},
    meta: options.metaSlug ? { dictSlug: options.metaSlug } : {},
  })
  return mount(ThinktankDictList, {
    props: options.slug ? { slug: options.slug } : {},
    global: { stubs: STUBS },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  grantPermissions([
    { code: 'codebook.thinktank_file_types', level: 'FULL' },
    { code: 'codebook.thinktank_provinces', level: 'FULL' },
    { code: 'codebook.thinktank_departments', level: 'FULL' },
    { code: 'system.audit', level: 'READ' },
  ])
  mocks.replace.mockReset().mockImplementation((target: { query: Record<string, unknown> }) => {
    if (mocks.route) mocks.route.query = target.query
    return Promise.resolve()
  })
  mocks.list.mockReset().mockResolvedValue({ items: [makeItem()], total: 1, page: 1, page_size: 20 })
  mocks.create.mockReset().mockResolvedValue(makeItem({ id: 'dict-2', name: '新类别', version: 1 }))
  mocks.update.mockReset().mockResolvedValue(makeItem({ id: 'dict-1', name: '经分（更新）', version: 3 }))
  mocks.remove.mockReset().mockResolvedValue({ deleted: true })
  mocks.importFile.mockReset().mockResolvedValue({ inserted: 2, updated: 0, skipped: 0, total: 2 })
  mocks.downloadFile.mockReset().mockResolvedValue(undefined)
  mocks.fetchFilterOptions.mockReset().mockResolvedValue({
    options: { name: { items: ['经分', '通报'], truncated: false } },
  })
  mocks.searchFilterOptions.mockReset().mockResolvedValue({ items: [] })
  mocks.runExcelImport.mockReset().mockImplementation(
    async (_file: File, importer: (onProgress: (p: number, s: 'upload' | 'parse') => void) => Promise<unknown>) =>
      importer(() => {}),
  )
  mocks.reportImportResult.mockReset()
  mocks.msgSuccess.mockReset()
  mocks.msgError.mockReset()
  mocks.confirm.mockReset().mockResolvedValue('confirm')
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('ThinktankDictList 智库专属码表复用页', () => {
  it('支持通过 route.meta.dictSlug 渲染页面元数据、骨架屏与单业务字段表格', async () => {
    let resolveList!: (value: unknown) => void
    mocks.list.mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve }))

    const wrapper = mountPage({ metaSlug: 'provinces', path: '/codebook/thinktank/provinces' })
    await nextTick()
    expect(wrapper.find('.page-title').text()).toBe('省份码表')
    expect(wrapper.find('.page-hint').text()).toContain('集团及全国 31 省')
    expect(wrapper.find('.audit-btn-stub').attributes('data-module')).toBe('codebook.thinktank_provinces')
    expect(wrapper.find('.table-skeleton-stub').exists()).toBe(true)

    resolveList({
      items: [makeItem({ id: 'p-1', dict_type: 'provinces', name: '广东省', updated_by_name: '李四' })],
      total: 1,
      page: 1,
      page_size: 20,
    })
    await flushPromises()

    expect(wrapper.find('.table-skeleton-stub').exists()).toBe(false)
    const cells = wrapper.findAll('.table-cell')
    expect(cells.map(c => c.attributes('data-label'))).toEqual(['省份名称', '更新时间', '操作人', '操作'])
    expect(cells[0]!.text()).toBe('广东省')
    expect(cells[2]!.text()).toBe('李四')
    expect(mocks.fetchFilterOptions).toHaveBeenCalledWith('/codebook/thinktank/provinces')
  })

  it('严格遵守 RBAC：只读角色隐藏新增/导入/操作列并禁用导出，导出角色启用导出', async () => {
    grantPermissions([{ code: 'codebook.thinktank_file_types', level: 'READ' }])
    const wrapper = mountPage({ slug: 'file-types' })
    await flushPromises()

    expect(wrapper.find('.page-actions').text()).not.toContain('新增')
    expect(wrapper.find('.import-btn-stub').exists()).toBe(false)
    expect(wrapper.find('.export-btn-stub').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.table-cell').map(c => c.attributes('data-label'))).toEqual(['文件类别', '更新时间', '操作人'])

    grantPermissions([{ code: 'codebook.thinktank_file_types', level: 'EXPORT' }])
    await nextTick()
    expect(wrapper.find('.export-btn-stub').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('.import-btn-stub').exists()).toBe(false)
  })

  it('支持关键词筛选查询与重置', async () => {
    const wrapper = mountPage({ slug: 'file-types' })
    await flushPromises()
    mocks.list.mockClear()

    fire(wrapper.findComponent({ name: 'FilterSelect' }), 'update:modelValue', ['经分'])
    await wrapper.find('.btn-search').trigger('click')
    await flushPromises()
    expect(mocks.list).toHaveBeenCalledWith('file-types', { keyword: ['经分'], page: 1, page_size: 20 })

    await wrapper.find('.btn-reset').trigger('click')
    await flushPromises()
    expect(mocks.list).toHaveBeenLastCalledWith('file-types', { keyword: [], page: 1, page_size: 20 })
  })

  it('支持新增校验、保存关闭锁、未保存提示与提交后刷新', async () => {
    let resolveCreate!: (val: ThinktankDictItem) => void
    mocks.create.mockImplementationOnce(() => new Promise((resolve) => { resolveCreate = resolve }))

    const wrapper = mountPage({ slug: 'file-types' })
    await flushPromises()
    mocks.list.mockClear()
    mocks.fetchFilterOptions.mockClear()

    const addBtn = wrapper.findAll('.page-actions .el-button-stub').find(b => b.text() === '新增')!
    await addBtn.trigger('click')
    await nextTick()
    expect(wrapper.find('.dialog-title').text()).toBe('新增文件类别')
    expect(wrapper.find('.editor-dirty').exists()).toBe(false)

    // 空白提交触发必填校验
    const submitBtn = () => wrapper.findAll('.dialog-footer .el-button-stub').find(b => b.text() === '创建')!
    await submitBtn().trigger('click')
    await flushPromises()
    expect(wrapper.find('.field-error').text()).toBe('请填写文件类别')
    expect(mocks.create).not.toHaveBeenCalled()

    // 填写内容后出现未保存标识，保存期间锁住弹窗关闭
    await wrapper.find('.el-input-stub').setValue('  行业报告  ')
    await nextTick()
    expect(wrapper.find('.editor-dirty').exists()).toBe(true)

    const clickPromise = submitBtn().trigger('click')
    await flushPromises()
    const dialog = wrapper.find('.el-dialog-stub')
    expect(dialog.attributes('data-close-modal')).toBe('false')
    expect(dialog.attributes('data-close-escape')).toBe('false')
    expect(dialog.attributes('data-show-close')).toBe('false')

    resolveCreate(makeItem({ id: 'dict-2', name: '行业报告', version: 1 }))
    await clickPromise
    await flushPromises()

    expect(mocks.create).toHaveBeenCalledWith('file-types', { name: '行业报告' })
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(false)
    expect(mocks.msgSuccess).toHaveBeenCalledWith('已新增')
    expect(mocks.list).toHaveBeenCalledWith('file-types', { keyword: [], page: 1, page_size: 20 })
    expect(mocks.fetchFilterOptions).toHaveBeenCalledWith('/codebook/thinktank/file-types')
  })

  it('支持编辑提交，并分别处理 409 版本冲突与 409 重名错误', async () => {
    const wrapper = mountPage({ slug: 'file-types' })
    await flushPromises()

    await wrapper.find('.row-action--primary').trigger('click')
    await nextTick()
    expect(wrapper.find('.dialog-title').text()).toBe('编辑文件类别')
    expect((wrapper.find('.el-input-stub').element as HTMLInputElement).value).toBe('经分')

    // 1) 版本冲突（409 非 DUPLICATE）：标记已展示并保留用户输入草稿
    const staleErr = new ApiRequestError({ status: 409, code: 'VERSION_CONFLICT', message: '版本已变更', requestId: 'req-1' })
    mocks.update.mockRejectedValueOnce(staleErr)
    await wrapper.find('.el-input-stub').setValue('经分新名称')
    const saveBtn = () => wrapper.findAll('.dialog-footer .el-button-stub').find(b => b.text() === '保存')!
    await saveBtn().trigger('click')
    await flushPromises()

    expect(wasShown(staleErr)).toBe(true)
    expect(wrapper.find('.el-alert-stub').text()).toContain('已被他人修改')
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)

    // 2) 重名冲突（409 DUPLICATE）：直接提示后端重名原因
    const dupErr = new ApiRequestError({ status: 409, code: 'DUPLICATE', message: '文件类别已存在', requestId: 'req-2' })
    mocks.update.mockRejectedValueOnce(dupErr)
    await saveBtn().trigger('click')
    await flushPromises()
    expect(wrapper.find('.el-alert-stub').text()).toBe('文件类别已存在')

    // 3) 正常保存成功
    await saveBtn().trigger('click')
    await flushPromises()
    expect(mocks.update).toHaveBeenLastCalledWith('file-types', 'dict-1', { name: '经分新名称', version: 2 })
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(false)
    expect(mocks.msgSuccess).toHaveBeenCalledWith('已保存')
  })

  it('删除前弹窗确认；取消不发请求，确认删除后刷新并在尾页删空时自动回退上一页', async () => {
    const wrapper = mountPage({ slug: 'file-types', query: { page: '2' } })
    await flushPromises()
    mocks.list.mockClear()

    // 取消删除
    mocks.confirm.mockRejectedValueOnce('cancel')
    await wrapper.find('.row-action--danger').trigger('click')
    await flushPromises()
    expect(mocks.remove).not.toHaveBeenCalled()

    // 确认删除第 2 页最后一条 -> 自动退回第 1 页并刷新
    mocks.confirm.mockResolvedValueOnce('confirm')
    await wrapper.find('.row-action--danger').trigger('click')
    await flushPromises()
    expect(mocks.remove).toHaveBeenCalledWith('file-types', 'dict-1')
    expect(mocks.msgSuccess).toHaveBeenCalledWith('已删除')
    expect(mocks.list).toHaveBeenCalledWith('file-types', { keyword: [], page: 1, page_size: 20 })
  })

  it('支持导入与按已生效筛选条件导出 Excel', async () => {
    const wrapper = mountPage({ slug: 'departments' })
    await flushPromises()

    // 导入
    const importBtn = wrapper.findComponent({ name: 'ImportButton' })
    const uploadFn = importBtn.props('upload') as (file: File) => Promise<boolean>
    const excelFile = new File(['dummy'], 'departments.xlsx')
    mocks.list.mockClear()
    const ret = await uploadFn(excelFile)
    expect(ret).toBe(false)
    expect(mocks.importFile).toHaveBeenCalledWith('departments', excelFile, expect.any(Function))
    expect(mocks.reportImportResult).toHaveBeenCalledWith(
      { inserted: 2, updated: 0, skipped: 0, total: 2 },
      '客户部门归属-跳过明细.xlsx',
    )
    expect(mocks.list).toHaveBeenCalledWith('departments', { keyword: [], page: 1, page_size: 20 })

    // 筛选生效后导出
    fire(wrapper.findComponent({ name: 'FilterSelect' }), 'update:modelValue', ['政企部'])
    await wrapper.find('.btn-search').trigger('click')
    await flushPromises()
    await wrapper.find('.export-btn-stub').trigger('click')
    await flushPromises()
    expect(mocks.downloadFile).toHaveBeenCalledWith(
      '/codebook/thinktank/departments/export',
      '客户部门归属码表.xlsx',
      { keyword: ['政企部'] },
    )
    expect(mocks.msgSuccess).toHaveBeenCalledWith('下载已开始，请查看浏览器下载列表')
  })

  it('切换 props.slug 或 route.meta.dictSlug 时关闭弹窗、清空筛选并重新加载新码表', async () => {
    const wrapper = mountPage({ slug: 'file-types' })
    await flushPromises()

    // 施加筛选并打开弹窗
    fire(wrapper.findComponent({ name: 'FilterSelect' }), 'update:modelValue', ['经分'])
    await wrapper.find('.btn-search').trigger('click')
    await flushPromises()
    const addBtn = wrapper.findAll('.page-actions .el-button-stub').find(b => b.text() === '新增')!
    await addBtn.trigger('click')
    await nextTick()
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)

    mocks.list.mockClear()
    mocks.fetchFilterOptions.mockClear()
    mocks.list.mockResolvedValueOnce({
      items: [makeItem({ id: 'p-1', dict_type: 'provinces', name: '北京市' })],
      total: 1,
      page: 1,
      page_size: 20,
    })

    // 切换 props.slug -> provinces
    await wrapper.setProps({ slug: 'provinces' })
    await flushPromises()

    expect(wrapper.find('.page-title').text()).toBe('省份码表')
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(false)
    expect(mocks.list).toHaveBeenCalledWith('provinces', { keyword: [], page: 1, page_size: 20 })
    expect(mocks.fetchFilterOptions).toHaveBeenCalledWith('/codebook/thinktank/provinces')
    expect(wrapper.find('.table-cell').text()).toBe('北京市')

    // 模拟路由切换（同一组件实例复用，仅 route.meta.dictSlug & route.path 变更）
    const routeWrapper = mountPage({ metaSlug: 'file-types', path: '/codebook/thinktank/file-types' })
    await flushPromises()
    mocks.list.mockClear()
    mocks.fetchFilterOptions.mockClear()

    mocks.route!.path = '/codebook/thinktank/departments'
    mocks.route!.query = {}
    mocks.route!.meta = { dictSlug: 'departments' }
    await flushPromises()

    expect(routeWrapper.find('.page-title').text()).toBe('客户部门归属码表')
    expect(mocks.list).toHaveBeenCalledWith('departments', { keyword: [], page: 1, page_size: 20 })
    expect(mocks.fetchFilterOptions).toHaveBeenCalledWith('/codebook/thinktank/departments')
  })
})
