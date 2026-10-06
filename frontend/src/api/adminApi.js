import client from './client';

export const adminApi = {
  getRoles: () => client.get('/auth/roles/'),
  getUsers: (params) => client.get('/auth/users/', { params }),
  getRoleAssignments: (params) => client.get('/auth/role-assignments/', { params }),
  assignRole: (data) => client.post('/auth/role-assignments/', data),
  revokeRole: (id, reason) => client.post(`/auth/role-assignments/${id}/revoke/`, { reason }),
  getDepartmentHODs: () => client.get('/auth/role-assignments/department-hods/'),
  saveDepartmentHODs: (assignments) => client.post('/auth/role-assignments/department-hods/', { assignments }),
};

export default adminApi;
