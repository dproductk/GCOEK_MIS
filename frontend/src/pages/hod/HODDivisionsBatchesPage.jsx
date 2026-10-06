import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import academicApi from '../../api/academicApi';
import studentApi from '../../api/studentApi';
import { LoadingState, ErrorState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';
import DataTable from '../../components/common/DataTable';

function divisionLetter(i) {
  return String.fromCharCode(65 + i);
}

export default function HODDivisionsBatchesPage() {
  const { user, hasRole } = useAuth();
  const isSysadmin = hasRole('SYSADMIN') || hasRole('ADMIN_HEAD');
  const isHOD = hasRole('HOD') && !isSysadmin;
  const canManage = isSysadmin || isHOD;

  const hodRole = user?.roles?.find((r) => r.codename === 'HOD');
  const hodDeptId = hodRole?.department_id;

  const [departments, setDepartments] = useState([]);
  const [years, setYears] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [divisions, setDivisions] = useState([]);
  const [batches, setBatches] = useState([]);
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);
  const [actionError, setActionError] = useState(null);

  const [selectedDept, setSelectedDept] = useState('');
  const [selectedYear, setSelectedYear] = useState('');
  const [selectedSem, setSelectedSem] = useState('');
  const [perDivision, setPerDivision] = useState(60);
  const [perBatch, setPerBatch] = useState(20);
  const [search, setSearch] = useState('');
  const [divFilter, setDivFilter] = useState('');

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    try {
      setLoading(true);
      setError(null);
      // allSettled: lab-batches endpoint may 404 if backend not restarted after migration
      const [deptRes, yearRes, semRes, divRes, batchRes, stuRes] = await Promise.allSettled([
        academicApi.getDepartments(),
        academicApi.getAcademicYears(),
        academicApi.getSemesters(),
        academicApi.getDivisions(),
        academicApi.getLabBatches(),
        studentApi.getStudents({ page_size: 250 }),
      ]);
      const deptList = deptRes.status === 'fulfilled' ? deptRes.value.data?.results || deptRes.value.data || [] : [];
      const yearList = yearRes.status === 'fulfilled' ? yearRes.value.data?.results || yearRes.value.data || [] : [];
      const semList = semRes.status === 'fulfilled' ? semRes.value.data?.results || semRes.value.data || [] : [];
      const divList = divRes.status === 'fulfilled' ? divRes.value.data?.results || divRes.value.data || [] : [];
      const batchList = batchRes.status === 'fulfilled' ? batchRes.value.data?.results || batchRes.value.data || [] : [];
      const stuList = stuRes.status === 'fulfilled' ? stuRes.value.data?.results || stuRes.value.data || [] : [];

      let finalDepts = deptList;
      let initialDept = selectedDept;

      if (isHOD && hodDeptId) {
        finalDepts = deptList.filter((d) => String(d.id) === String(hodDeptId));
        initialDept = hodDeptId;
      } else if (isHOD && deptList.length > 0 && !hodDeptId) {
        // Fallback for HOD with CSE default
        const cse = deptList.find((d) => d.code === 'CSE') || deptList[0];
        finalDepts = [cse];
        initialDept = cse.id;
      } else if (!initialDept && deptList.length > 0) {
        initialDept = deptList[0].id;
      }

      setDepartments(finalDepts);
      setSelectedDept(initialDept);
      setYears(yearList);
      setSemesters(semList);
      setDivisions(divList);
      setBatches(batchList);
      setStudents(stuList);
      if (batchRes.status !== 'fulfilled') {
        setActionError('Lab batches API not reachable — restart backend server to load new /lab-batches/ endpoint. Divisions still work.');
      }
      const curYear = yearList.find((y) => y.is_current) || yearList[0];
      if (!selectedYear && curYear) setSelectedYear(curYear.id);
      if (!selectedSem && semList.length > 0) {
        const s1 = semList.find((s) => s.number === 1) || semList[0];
        setSelectedSem(s1.id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load divisions & batches.');
    } finally {
      setLoading(false);
    }
  };

  const scopedDivisions = useMemo(() => {
    return divisions.filter((d) => {
      const deptMatch = selectedDept ? String(d.department) === String(selectedDept) : true;
      const yearMatch = selectedYear ? String(d.academic_year) === String(selectedYear) : true;
      const semMatch = selectedSem ? String(d.semester) === String(selectedSem) : true;
      return deptMatch && yearMatch && semMatch;
    });
  }, [divisions, selectedDept, selectedYear, selectedSem]);

  const [streamFilter, setStreamFilter] = useState('ALL'); // 'ALL' | 'DSY' | 'REGULAR' | 'UNASSIGNED'

  const scopedStudents = useMemo(() => {
    let list = students;
    if (selectedDept) {
      const activeDeptObj = departments.find((d) => String(d.id) === String(selectedDept));
      if (activeDeptObj?.code) {
        list = list.filter((s) => s.department_code === activeDeptObj.code);
      }
    }
    if (selectedSem) {
      const activeSemObj = semesters.find((s) => String(s.id) === String(selectedSem));
      if (activeSemObj) {
        list = list.filter((s) => s.semester_number === activeSemObj.number);
      }
    }
    if (streamFilter === 'DSY') {
      list = list.filter((s) => s.is_direct_second_year);
    } else if (streamFilter === 'REGULAR') {
      list = list.filter((s) => !s.is_direct_second_year);
    } else if (streamFilter === 'UNASSIGNED') {
      list = list.filter((s) => !s.division_id || !s.lab_batch_id);
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((s) =>
        `${s.display_name || ''} ${s.enrollment_no || ''} ${s.application_id || ''}`.toLowerCase().includes(q)
      );
    }
    return list;
  }, [students, selectedDept, departments, selectedSem, semesters, streamFilter, search]);

  const filteredByDiv = useMemo(() => {
    if (!divFilter) return scopedStudents;
    return scopedStudents.filter((s) => (s.division_name || 'A') === divFilter);
  }, [scopedStudents, divFilter]);

  const numDivisionsNeeded = Math.max(1, Math.ceil((scopedStudents.length || 0) / (Number(perDivision) || 60)));

  const handleAssign = async (studentId, divisionId, labBatchId) => {
    try {
      setActionMsg(null);
      setActionError(null);
      await studentApi.assignDivision(studentId, {
        division_id: divisionId || null,
        lab_batch_id: labBatchId || null,
      });

      const divObj = divisions.find((d) => String(d.id) === String(divisionId));
      const batchObj = batches.find((b) => String(b.id) === String(labBatchId));

      setStudents((prev) =>
        prev.map((s) => {
          if (s.id === studentId) {
            return {
              ...s,
              division_id: divisionId || null,
              division_name: divObj ? divObj.name : null,
              lab_batch_id: labBatchId || null,
              lab_batch_name: batchObj ? batchObj.name : null,
            };
          }
          return s;
        })
      );
      setActionMsg('Student assignment updated successfully.');
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to update student assignment.');
    }
  };

  const handleCreateDivisions = async () => {
    if (!canManage) {
      setActionError('Division creation is restricted to HOD / Sysadmin.');
      return;
    }
    if (isHOD && hodDeptId && String(selectedDept) !== String(hodDeptId)) {
      setActionError('HOD is strictly restricted to creating divisions within their assigned department.');
      return;
    }
    try {
      setActionMsg(null);
      setActionError(null);
      if (!selectedDept || !selectedYear || !selectedSem) {
        setActionError('Select department, academic year and semester first.');
        return;
      }
      const existing = new Set(scopedDivisions.map((d) => d.name));
      const toCreate = [];
      for (let i = 0; i < numDivisionsNeeded; i += 1) {
        const name = divisionLetter(i);
        if (!existing.has(name)) toCreate.push(name);
      }
      if (toCreate.length === 0) {
        setActionMsg('Divisions already exist for this selection.');
        return;
      }
      for (const name of toCreate) {
        await academicApi.createDivision({
          department: selectedDept,
          academic_year: selectedYear,
          semester: selectedSem,
          name,
          seat_capacity: Number(perDivision) || 60,
        });
      }
      setActionMsg(`Created ${toCreate.length} division(s): ${toCreate.join(', ')}`);
      loadAll();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to create divisions. HOD can only create for own department.');
    }
  };

  const handleCreateBatches = async () => {
    if (!canManage) {
      setActionError('Batch creation is restricted to HOD / Sysadmin. Log in as hod_cse.');
      return;
    }
    try {
      setActionMsg(null);
      setActionError(null);
      if (scopedDivisions.length === 0) {
        setActionError('Create divisions first (Step 1).');
        return;
      }
      let created = 0;
      for (const div of scopedDivisions) {
        const existing = batches.filter((b) => String(b.division) === String(div.id)).map((b) => b.name);
        const perDivCount = Math.ceil((scopedStudents.length / scopedDivisions.length || 0) / (Number(perBatch) || 20));
        const need = Math.max(1, perDivCount);
        for (let i = 0; i < need; i += 1) {
          const batchName = `${div.name}${i + 1}`;
          if (!existing.includes(batchName)) {
            await academicApi.createLabBatch({
              division: div.id,
              name: batchName,
              seat_capacity: Number(perBatch) || 20,
            });
            created += 1;
          }
        }
      }
      setActionMsg(created === 0 ? 'Lab batches already exist.' : `Created ${created} lab batch(es) like A1, A2, A3.`);
      loadAll();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to create lab batches.');
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading divisions & batches..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2rem' }}>
        <ErrorState title="Failed to load" message={error} onRetry={loadAll} />
      </div>
    );
  }

  const columns = [
    {
      header: 'No.',
      width: '56px',
      align: 'center',
      render: (_, idx) => <span style={{ color: '#64748b', fontWeight: 600 }}>{idx + 1}</span>,
    },
    {
      header: 'Student',
      render: (row) => (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{ fontWeight: 700, color: '#0f172a' }}>{row.display_name || `${row.first_name} ${row.last_name}`}</span>
            {row.is_direct_second_year && (
              <span
                style={{
                  fontSize: '0.625rem',
                  fontWeight: 800,
                  padding: '0.1rem 0.35rem',
                  borderRadius: '4px',
                  backgroundColor: '#f3e8ff',
                  color: '#7e22ce',
                  border: '1px solid #d8b4fe',
                }}
                title="Direct Second Year (Lateral Entry)"
              >
                ⚡ DSY
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#64748b' }}>
            {row.enrollment_no || row.application_id} • Sem {row.semester_number || 1}
          </div>
        </div>
      ),
    },
    {
      header: 'Division Allocation',
      render: (row) => {
        return (
          <select
            className="edvana-input"
            value={row.division_id || ''}
            onChange={(e) => handleAssign(row.id, e.target.value || null, row.lab_batch_id || null)}
            style={{
              padding: '0.3rem 0.6rem',
              fontSize: '0.8125rem',
              height: '34px',
              minWidth: '130px',
              fontWeight: 600,
              backgroundColor: row.division_id ? '#ffffff' : '#fffbeb',
              borderColor: row.division_id ? '#cbd5e1' : '#fde68a',
            }}
          >
            <option value="">Unassigned</option>
            {scopedDivisions.map((d) => (
              <option key={d.id} value={d.id}>
                Division {d.name}
              </option>
            ))}
          </select>
        );
      },
    },
    {
      header: 'Lab Batch Allocation',
      render: (row) => {
        const divBatches = batches.filter(
          (b) => String(b.division) === String(row.division_id) || String(b.division_id) === String(row.division_id)
        );
        return (
          <select
            className="edvana-input"
            disabled={!row.division_id}
            value={row.lab_batch_id || ''}
            onChange={(e) => handleAssign(row.id, row.division_id, e.target.value || null)}
            style={{
              padding: '0.3rem 0.6rem',
              fontSize: '0.8125rem',
              height: '34px',
              minWidth: '130px',
              fontWeight: 600,
              backgroundColor: !row.division_id ? '#f1f5f9' : row.lab_batch_id ? '#ffffff' : '#fffbeb',
              borderColor: row.lab_batch_id ? '#cbd5e1' : '#fde68a',
            }}
            title={!row.division_id ? 'Assign division first' : 'Select lab batch'}
          >
            <option value="">{!row.division_id ? 'Assign Div First' : 'Unassigned'}</option>
            {divBatches.map((b) => (
              <option key={b.id} value={b.id}>
                Batch {b.name}
              </option>
            ))}
          </select>
        );
      },
    },
    {
      header: 'Status',
      render: (row) => {
        const isFullyAssigned = Boolean(row.division_id && row.lab_batch_id);
        const isPartiallyAssigned = Boolean(row.division_id && !row.lab_batch_id);
        return (
          <span
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              padding: '0.2rem 0.55rem',
              borderRadius: '9999px',
              backgroundColor: isFullyAssigned ? '#dcfce7' : isPartiallyAssigned ? '#eff6ff' : '#fef3c7',
              color: isFullyAssigned ? '#15803d' : isPartiallyAssigned ? '#1d4ed8' : '#b45309',
            }}
          >
            {isFullyAssigned
              ? `Div ${row.division_name} • ${row.lab_batch_name}`
              : isPartiallyAssigned
              ? `Div ${row.division_name} (No Batch)`
              : 'Needs Allocation'}
          </span>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Home', to: '/dashboard' }, { label: 'Student Divisions & Batches' }]}
        title="Divisions"
        subtitle={`${scopedStudents.length} students found. Split them into divisions and lab batches.`}
      />
      <div className="edvana-banner-overlap">
        {(actionMsg || actionError) && (
          <div
            style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              fontSize: '0.875rem',
              backgroundColor: actionError ? '#fef2f2' : '#f0fdf4',
              border: `1px solid ${actionError ? '#fecaca' : '#bbf7d0'}`,
              color: actionError ? '#dc2626' : '#16a34a',
            }}
          >
            {actionError || actionMsg}
          </div>
        )}

        <div className="edvana-card" style={{ padding: '1.5rem 1.75rem', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <label style={{ fontWeight: 600 }}>Department:</label>
            {isHOD ? (
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.45rem 0.85rem',
                  backgroundColor: '#eff6ff',
                  borderRadius: '6px',
                  border: '1px solid #bfdbfe',
                  fontWeight: 600,
                  color: '#1e40af',
                  fontSize: '0.85rem',
                }}
              >
                <span>{departments[0]?.name || 'Department'} ({departments[0]?.code || 'CSE'})</span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    background: '#dbeafe',
                    color: '#1e3a8a',
                    padding: '0.1rem 0.45rem',
                    borderRadius: '4px',
                    fontWeight: 700,
                  }}
                >
                  Locked to HOD Scope
                </span>
              </div>
            ) : (
              <select className="edvana-input" value={selectedDept} onChange={(e) => setSelectedDept(e.target.value)} style={{ minWidth: '220px' }}>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.code})
                  </option>
                ))}
              </select>
            )}
            <select className="edvana-input" value={selectedYear} onChange={(e) => setSelectedYear(e.target.value)}>
              {years.map((y) => (
                <option key={y.id} value={y.id}>
                  {y.code}
                </option>
              ))}
            </select>
            <select className="edvana-input" value={selectedSem} onChange={(e) => setSelectedSem(e.target.value)}>
              {semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  Sem {s.number}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
          <div className="edvana-card" style={{ padding: '1.25rem' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>TOTAL STUDENTS</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800 }}>{scopedStudents.length}</div>
          </div>
          <div className="edvana-card" style={{ padding: '1.25rem' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>DIVISIONS</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800 }}>{scopedDivisions.length}</div>
            <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{scopedDivisions.map((d) => d.name).join(', ')}</div>
          </div>
          <div className="edvana-card" style={{ padding: '1.25rem' }}>
            <div style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 600 }}>LAB BATCHES</div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800 }}>{batches.length}</div>
          </div>
        </div>

        {canManage && (
          <div className="edvana-card" style={{ padding: '1.5rem 1.75rem', marginBottom: '1.25rem' }}>
            <h3 style={{ margin: '0 0 1rem' }}>Setup in 2 steps</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '12px', padding: '1.25rem' }}>
                <h4 style={{ margin: '0 0 0.5rem' }}>Step 1 — Make divisions</h4>
                <p style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                  Example: {perDivision} per division puts all {scopedStudents.length} students in {numDivisionsNeeded} division(s).
                </p>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '1rem' }}>
                  <label style={{ fontSize: '0.8125rem' }}>Students per division</label>
                  <input type="number" className="edvana-input" value={perDivision} onChange={(e) => setPerDivision(e.target.value)} style={{ width: '90px' }} />
                  <button type="button" className="edvana-btn edvana-btn-primary" onClick={handleCreateDivisions}>
                    Create divisions
                  </button>
                </div>
              </div>
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '12px', padding: '1.25rem' }}>
                <h4 style={{ margin: '0 0 0.5rem' }}>Step 2 — Make lab batches</h4>
                <p style={{ fontSize: '0.8125rem', color: '#64748b' }}>Splits each division into small groups like A1, A2, A3.</p>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '1rem' }}>
                  <label style={{ fontSize: '0.8125rem' }}>Students per batch</label>
                  <input type="number" className="edvana-input" value={perBatch} onChange={(e) => setPerBatch(e.target.value)} style={{ width: '90px' }} />
                  <button type="button" className="edvana-btn edvana-btn-outline" onClick={handleCreateBatches}>
                    Create batches
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="edvana-card" style={{ padding: '1.5rem 1.75rem' }}>
          <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
            <input
              type="text"
              className="edvana-input"
              disabled={false}
              placeholder="Search name, enrollment no"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ maxWidth: '280px' }}
            />
            <select className="edvana-input" disabled={false} value={divFilter} onChange={(e) => setDivFilter(e.target.value)}>
              <option value="">All divisions</option>
              {scopedDivisions.map((d) => (
                <option key={d.id} value={d.name}>
                  Div {d.name}
                </option>
              ))}
            </select>
            <span style={{ fontSize: '0.8125rem', color: '#64748b', marginLeft: 'auto' }}>
              Showing {filteredByDiv.length} of {scopedStudents.length} students
            </span>
          </div>
          <DataTable columns={columns} data={filteredByDiv} keyField="id" emptyMessage="No students found." />
        </div>
      </div>
    </>
  );
}
