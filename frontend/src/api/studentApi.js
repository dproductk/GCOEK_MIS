import client from './client';

export const studentApi = {
  /**
   * List students with scope-aware filtering and search.
   */
  getStudents: (params = {}) => client.get('/students/', { params }),

  /**
   * Retrieve full composed profile of a student.
   */
  getStudentProfile: (id) => client.get(`/students/${id}/`),

  /**
   * Retrieve current authenticated student's own profile.
   */
  getMyProfile: () => client.get('/students/me/'),

  /**
   * Update own profile (student self-service).
   * Backend whitelists editable fields; identifiers, admission data,
   * Aadhaar number and verified documents are always locked.
   */
  updateMyProfile: (data) => client.patch('/students/me/update/', data),

  /**
   * Reveal unmasked sensitive details (requires permission + audit reason).
   */
  revealSensitive: (id, reason) =>
    client.post(`/students/${id}/reveal/`, { reason }),

  /**
   * Assign or edit a student's division and/or lab batch (HOD/Admin authority).
   */
  assignDivision: (id, payload) => {
    const body = typeof payload === 'object' && payload !== null ? payload : { division_id: payload };
    return client.post(`/students/${id}/assign-division/`, body);
  },
};

export default studentApi;
