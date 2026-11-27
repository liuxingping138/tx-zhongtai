import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockHttp = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}))
const mockRequest = vi.hoisted(() => vi.fn((p: Promise<unknown>) => p))
const mockPostExcelImport = vi.hoisted(() => vi.fn())

vi.mock('@/api/http', () => ({
  http: mockHttp,
  request: mockRequest,
}))
vi.mock('@/api/excelImport', () => ({
  postExcelImport: mockPostExcelImport,
}))

import * as api from '@/api/thinktank'

describe('thinktank API client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockHttp.get.mockResolvedValue({ data: new Blob(), headers: {} })
    mockHttp.post.mockResolvedValue({})
    mockHttp.patch.mockResolvedValue({})
    mockHttp.delete.mockResolvedValue({})
    mockPostExcelImport.mockResolvedValue({ imported: 1, skipped: 0 })
  })

  it('calls all knowledge endpoints cleanly', async () => {
    const file = new File(['abc'], 'a.pdf')
    await api.getKnowledgeAccess()
    await api.listKnowledge({ page: 1 })
    await api.previewKnowledge('k1')
    await api.fetchKnowledgeContentBlob('k1')
    await api.downloadKnowledgeBlob('k1')
    await api.favoriteKnowledge('k1')
    await api.unfavoriteKnowledge('k1')
    await api.listKnowledgeLogs('k1', { page: 1, page_size: 10 })
    await api.updateKnowledge('k1', { file_name: 'new', version: 1 })
    await api.deleteKnowledge('k1')
    await api.uploadKnowledgeFile(file)
    await api.uploadKnowledgeFile(file, { file_type: '产品' })
    await api.uploadKnowledgeTags(file)
    await api.exportUndefinedKnowledge()

    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge/access')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge', { params: { page: 1 } })
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge/k1/preview')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge/k1/content', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge/k1/download', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.post).toHaveBeenCalledWith('/thinktank/knowledge/k1/favorite')
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/knowledge/k1/favorite')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge/k1/logs', { params: { page: 1, page_size: 10 } })
    expect(mockHttp.patch).toHaveBeenCalledWith('/thinktank/knowledge/k1', { file_name: 'new', version: 1 })
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/knowledge/k1')
    expect(mockHttp.post).toHaveBeenCalledWith('/thinktank/knowledge/upload', expect.any(FormData), expect.objectContaining({ params: { file_type: '产品' } }))
    expect(mockPostExcelImport).toHaveBeenCalledWith('/thinktank/knowledge/upload-tags', file, undefined, 180_000)
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/knowledge/export-undefined', expect.objectContaining({ responseType: 'blob' }))
  })

  it('calls all report endpoints cleanly', async () => {
    const file = new File(['abc'], 'r.pdf')
    await api.listReports({ report_name: ['年报'] })
    await api.previewReport('r1')
    await api.fetchReportContentBlob('r1')
    await api.downloadReportBlob('r1')
    await api.favoriteReport('r1')
    await api.unfavoriteReport('r1')
    await api.listReportLogs('r1', { page: 2 })
    await api.updateReport('r1', { report_name: '年报', version: 2 })
    await api.deleteReport('r1')
    await api.uploadReportFile(file)
    await api.uploadReportFile(file, { report_type: '行业研究报告' })
    await api.uploadReportTags(file)
    await api.exportUndefinedReports()

    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports', { params: { report_name: ['年报'] } })
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports/r1/preview')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports/r1/content', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports/r1/download', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.post).toHaveBeenCalledWith('/thinktank/reports/r1/favorite')
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/reports/r1/favorite')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports/r1/logs', { params: { page: 2 } })
    expect(mockHttp.patch).toHaveBeenCalledWith('/thinktank/reports/r1', { report_name: '年报', version: 2 })
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/reports/r1')
    expect(mockHttp.post).toHaveBeenCalledWith('/thinktank/reports/upload', expect.any(FormData), expect.objectContaining({ params: { report_type: '行业研究报告' } }))
    expect(mockPostExcelImport).toHaveBeenCalledWith('/thinktank/reports/upload-tags', file, undefined, 180_000)
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports/export-undefined', expect.objectContaining({ responseType: 'blob' }))
  })

  it('calls all proposal and favorites endpoints cleanly', async () => {
    const file = new File(['abc'], 'p.pptx')
    await api.listProposals({ result_status: ['中标'] })
    await api.previewProposal('p1')
    await api.fetchProposalContentBlob('p1')
    await api.downloadProposalBlob('p1')
    await api.favoriteProposal('p1')
    await api.unfavoriteProposal('p1')
    await api.listProposalLogs('p1')
    await api.updateProposal('p1', { proposal_name: '方案', version: 3 })
    await api.deleteProposal('p1')
    await api.uploadProposalFile(file)
    await api.uploadProposalFile(file, { proposal_type: '投标方案' })
    await api.uploadProposalTags(file)
    await api.exportUndefinedProposals()
    await api.listThinktankFavorites()
    await api.listThinktankFavorites({ library: 'reports', keyword: '云', page: 1, page_size: 20 })
    await api.unfavoriteThinktankItem('proposals', 'p1')
    await api.downloadThinktankItemBlob('reports', 'r1')

    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/proposals', { params: { result_status: ['中标'] } })
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/proposals/p1/preview')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/proposals/p1/content', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/proposals/p1/download', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.post).toHaveBeenCalledWith('/thinktank/proposals/p1/favorite')
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/proposals/p1/favorite')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/proposals/p1/logs', { params: undefined })
    expect(mockHttp.patch).toHaveBeenCalledWith('/thinktank/proposals/p1', { proposal_name: '方案', version: 3 })
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/proposals/p1')
    expect(mockHttp.post).toHaveBeenCalledWith('/thinktank/proposals/upload', expect.any(FormData), expect.objectContaining({ params: { proposal_type: '投标方案' } }))
    expect(mockPostExcelImport).toHaveBeenCalledWith('/thinktank/proposals/upload-tags', file, undefined, 180_000)
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/proposals/export-undefined', expect.objectContaining({ responseType: 'blob' }))
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/favorites', { params: {} })
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/favorites', {
      params: { library: 'reports', keyword: '云', page: 1, page_size: 20 },
    })
    expect(mockHttp.delete).toHaveBeenCalledWith('/thinktank/proposals/p1/favorite')
    expect(mockHttp.get).toHaveBeenCalledWith('/thinktank/reports/r1/download', expect.objectContaining({ responseType: 'blob' }))
  })
})
