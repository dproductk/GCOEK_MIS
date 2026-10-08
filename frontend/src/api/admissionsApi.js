import client from './client';

export const admissionsApi = {
  uploadFile: (formData) =>
    client.post('/admissions/batches/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  commitBatch: (batchId) =>
    client.post(`/admissions/batches/${batchId}/commit/`),

  getBatches: () => client.get('/admissions/batches/'),

  getBatchDetails: (batchId) =>
    client.get(`/admissions/batches/${batchId}/`),

  deleteBatch: (batchId, reason) =>
    client.delete(`/admissions/batches/${batchId}/delete/`, { data: { reason } }),

  getPendingIntakes: () => client.get('/admissions/batches/pending-intakes/'),
};

export default admissionsApi;
