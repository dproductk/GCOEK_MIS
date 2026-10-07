import client from './client';

export const auditApi = {
  getAuditLogs: (params) => client.get('/audit/logs/', { params }),
  // CSV archival export. Honors the same filters as getAuditLogs.
  // Returns a Blob — caller triggers the browser download. Server caps
  // at 10,000 newest rows; narrow date_from/date_to for larger archives.
  exportAuditLogs: (params) =>
    client.get('/audit/logs/export/', { params, responseType: 'blob' }),
};

export default auditApi;
