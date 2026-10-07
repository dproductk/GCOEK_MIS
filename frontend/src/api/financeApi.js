import client from './client';

export const financeApi = {
  // Fee Heads
  getFeeHeads: (params) => client.get('/finance/fee-heads/', { params }),
  createFeeHead: (data) => client.post('/finance/fee-heads/', data),
  updateFeeHead: (id, data) => client.patch(`/finance/fee-heads/${id}/`, data),
  deleteFeeHead: (id) => client.delete(`/finance/fee-heads/${id}/`),

  // Payment Ledger & Desk
  getPaymentLedgers: (params) => client.get('/finance/ledger/', { params }),
  recordPayment: (data) => client.post('/finance/ledger/', data),
  getPaymentDetail: (id) => client.get(`/finance/ledger/${id}/`),
  getMyPayments: () => client.get('/finance/ledger/my-payments/'),
  getFinanceAnalytics: (params) => client.get('/finance/ledger/analytics/', { params }),

  // Fee Assessments (Set Fee backed by the ledger database, not browser storage)
  getAssessments: (params) => client.get('/finance/assessments/', { params }),
  setAssessment: (data) => client.post('/finance/assessments/', data),
  updateAssessment: (id, data) => client.patch(`/finance/assessments/${id}/`, data),
  toggleOnlinePayment: (id, data) => client.post(`/finance/assessments/${id}/toggle-online-payment/`, data),

  // Online Payment Gateway (Easebuzz)
  getOnlinePaymentStatus: () => client.get('/finance/online-payment/status/'),
  initiateOnlinePayment: (data = {}, headers = {}) => client.post('/finance/online-payment/initiate/', data, { headers }),
  getPaymentAttempt: (id) => client.get(`/finance/online-payment/attempt/${id}/`),
  verifyPaymentAttempt: (id) => client.post(`/finance/online-payment/attempt/${id}/verify/`),
  getOnlinePaymentTracker: (params) => client.get('/finance/online-payment/tracker/', { params }),
};

export default financeApi;

