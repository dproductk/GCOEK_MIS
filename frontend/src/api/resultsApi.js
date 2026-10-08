import client from './client';

export const resultsApi = {
  getMyResults: () => client.get('/results/semester-results/my-results/'),

  getSemesterResults: (params = {}) =>
    client.get('/results/semester-results/', { params }),

  getEligibilities: (params = {}) =>
    client.get('/results/eligibility/', { params }),

  getClasses: (params = {}) =>
    client.get('/results/eligibility/classes/', { params }),

  getClassRoster: (divisionId) =>
    client.get('/results/eligibility/class-roster/', { params: { division_id: divisionId } }),

  startClassVerification: (divisionId) =>
    client.post('/results/eligibility/start-class-verification/', { division_id: divisionId }),

  reviewClassTeacher: (id, status, remarks = '') =>
    client.post(`/results/eligibility/${id}/review-class-teacher/`, {
      status,
      remarks,
    }),

  initializeEligibility: (data = {}) =>
    client.post('/results/eligibility/initialize/', data),

  getGraduationPending: () =>
    client.get('/results/semester-results/graduation-pending/'),

  confirmGraduation: (id, reason) =>
    client.post(`/results/semester-results/${id}/confirm-graduation/`, { reason }),

  submitMarks: (data) => client.post('/results/semester-results/submit-marks/', data),

  getEligibleCandidates: () => client.get('/results/eligibility/eligible-candidates/'),

  endorseHOD: (id, status, remarks = '') =>
    client.post(`/results/eligibility/${id}/endorse-hod/`, {
      status,
      remarks,
    }),

  getAdmissionFormData: (params = {}) =>
    client.get('/results/eligibility/admission-form-data/', { params }),

  downloadAdmissionFormPdf: (params = {}) =>
    client.get('/results/eligibility/admission-form-pdf/', {
      params,
      responseType: 'blob',
    }),
};

export default resultsApi;
