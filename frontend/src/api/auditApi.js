import client from './client';

export const auditApi = {
  getAuditLogs: (params) => client.get('/audit/logs/', { params }),
};

export default auditApi;
