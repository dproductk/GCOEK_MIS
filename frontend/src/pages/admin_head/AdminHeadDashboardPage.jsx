import React, { useState, useEffect } from 'react';
import { 
  Building2, Users, GraduationCap, IndianRupee, 
  TrendingUp, ShieldCheck, FileCheck, CreditCard, ArrowRight
} from 'lucide-react';
import { Link } from 'react-router-dom';
import financeApi from '../../api/financeApi';
import studentApi from '../../api/studentApi';
import facultyApi from '../../api/facultyApi';
import admissionsApi from '../../api/admissionsApi';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import Badge from '../../components/common/Badge';
import { LoadingState } from '../../components/common/StateDisplays';

export default function AdminHeadDashboardPage() {
  const [stats, setStats] = useState({
    totalStudents: 0,
    totalFaculty: 0,
    financeAnalytics: null,
    recentBatches: [],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      studentApi.getStudents().catch(() => ({ data: { count: 0 } })),
      facultyApi.getFacultyList ? facultyApi.getFacultyList().catch(() => ({ data: { count: 0 } })) : facultyApi.getFaculty().catch(() => ({ data: { count: 0 } })),
      financeApi.getFinanceAnalytics().catch(() => ({ data: null })),
      admissionsApi.getBatches().catch(() => ({ data: [] }))
    ]).then(([stuRes, facRes, finRes, batchRes]) => {
      setStats({
        totalStudents: stuRes.data?.count || (Array.isArray(stuRes.data) ? stuRes.data.length : 0),
        totalFaculty: facRes.data?.count || (Array.isArray(facRes.data) ? facRes.data.length : 0),
        financeAnalytics: finRes.data,
        recentBatches: batchRes.data?.results || batchRes.data || []
      });
    }).finally(() => {
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading administrative console..." />
      </div>
    );
  }

  const collectedAmount = stats.financeAnalytics?.total_collected ?? 0;
  const collectedDisplay = Number(collectedAmount).toLocaleString('en-IN');

  const balanceAmount = stats.financeAnalytics?.total_balance ?? 0;
  const balanceDisplay = Number(balanceAmount).toLocaleString('en-IN');

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: 'Home', to: '/dashboard' },
          { label: 'Administration' },
        ]}
        title="Administrative Console"
        subtitle="Executive oversight of admissions, student directories, faculty cadre strength, and institutional fee collection."
        actions={
          <div style={{ display: 'flex', gap: '0.625rem', flexWrap: 'wrap' }}>
            <Link
              to="/students"
              className="edvana-btn"
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.16)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                padding: '0.5rem 0.875rem',
              }}
            >
              <Users size={15} />
              <span>Student Directory</span>
            </Link>
            <Link
              to="/admissions/import"
              className="edvana-btn"
              style={{
                backgroundColor: '#ffffff',
                color: '#1d4ed8',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '0.8125rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.45rem',
                padding: '0.5rem 1rem',
              }}
            >
              <FileCheck size={15} />
              <span>Excel Ingestion</span>
            </Link>
          </div>
        }
      />

      <div className="edvana-banner-overlap">
        {/* KPI Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '1.25rem',
            marginBottom: '1.5rem',
          }}
        >
          <StatCard
            label="Total Enrolled"
            value={stats.totalStudents || 0}
            hint="Autonomous B.Tech Students"
            icon={GraduationCap}
            color="var(--edvana-brand)"
            trend="Active Registry"
          />

          <StatCard
            label="Faculty Strength"
            value={stats.totalFaculty || 0}
            hint="Teaching & Research Cadre"
            icon={Users}
            color="var(--edvana-info)"
            trend="Approved Cadre"
          />

          <StatCard
            label="Revenue Realized"
            value={`₹${collectedDisplay}`}
            hint="Tuition & Development Fees"
            icon={IndianRupee}
            color="var(--edvana-success)"
            trend="Current Fiscal"
          />

          <StatCard
            label="Outstanding Dues"
            value={`₹${balanceDisplay}`}
            hint="Pending Student Dues"
            icon={TrendingUp}
            color="var(--edvana-warning)"
            trend="Ledger Balance"
          />
        </div>

        {/* Quick Access Modules */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '1.5rem',
          }}
        >
          <Link
            to="/admissions/import"
            className="edvana-card"
            style={{
              textDecoration: 'none',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              transition: 'transform 0.15s ease, box-shadow 0.15s ease',
            }}
          >
            <div>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 'var(--edvana-radius-md)',
                  backgroundColor: 'var(--edvana-brand-soft)',
                  color: 'var(--edvana-brand)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1rem',
                  border: '1px solid var(--edvana-brand-soft-border)',
                }}
              >
                <FileCheck size={22} />
              </div>
              <h3 className="edvana-card-title" style={{ fontSize: '1.05rem', marginBottom: '0.35rem' }}>
                DTE Admissions & DSY Ingestion
              </h3>
              <p className="edvana-card-description">
                Import First Year (FY) and Direct Second Year (DSY) government candidate lists into core student rolls.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '1.25rem', color: 'var(--edvana-brand)', fontWeight: 600, fontSize: '0.8125rem' }}>
              <span>Open Ingestion Engine</span>
              <ArrowRight size={15} />
            </div>
          </Link>

          <Link
            to="/finance/analytics"
            className="edvana-card"
            style={{
              textDecoration: 'none',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              transition: 'transform 0.15s ease, box-shadow 0.15s ease',
            }}
          >
            <div>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 'var(--edvana-radius-md)',
                  backgroundColor: 'oklch(0.95 0.04 300)',
                  color: 'oklch(0.55 0.22 300)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1rem',
                  border: '1px solid oklch(0.88 0.08 300)',
                }}
              >
                <CreditCard size={22} />
              </div>
              <h3 className="edvana-card-title" style={{ fontSize: '1.05rem', marginBottom: '0.35rem' }}>
                Finance & Payment Analytics
              </h3>
              <p className="edvana-card-description">
                Real-time ledger audit, payment channel distributions, and fee recovery performance breakdown.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '1.25rem', color: 'oklch(0.55 0.22 300)', fontWeight: 600, fontSize: '0.8125rem' }}>
              <span>View Financial Ledger</span>
              <ArrowRight size={15} />
            </div>
          </Link>

          <Link
            to="/admin/audit"
            className="edvana-card"
            style={{
              textDecoration: 'none',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              transition: 'transform 0.15s ease, box-shadow 0.15s ease',
            }}
          >
            <div>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 'var(--edvana-radius-md)',
                  backgroundColor: 'var(--edvana-success-soft)',
                  color: 'var(--edvana-success)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '1rem',
                  border: '1px solid var(--edvana-success-border)',
                }}
              >
                <ShieldCheck size={22} />
              </div>
              <h3 className="edvana-card-title" style={{ fontSize: '1.05rem', marginBottom: '0.35rem' }}>
                Security & Audit Trail
              </h3>
              <p className="edvana-card-description">
                Immutable security logs of sensitive Aadhaar and bank reveals, grade endorsements, and role permissions.
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '1.25rem', color: 'var(--edvana-success)', fontWeight: 600, fontSize: '0.8125rem' }}>
              <span>Review Audit Trail</span>
              <ArrowRight size={15} />
            </div>
          </Link>
        </div>
      </div>
    </>
  );
}

