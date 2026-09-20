import { createElement } from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';

import { AppShell } from '../components/layout/AppShell';
import { ArchivePage } from '../modules/archive/ArchivePage';
import { DashboardPage } from '../modules/dashboard/DashboardPage';
import { InstrumentsPage } from '../modules/instruments/InstrumentsPage';
import { JobDetailPage } from '../modules/jobs/JobDetailPage';
import { JobsPage } from '../modules/jobs/JobsPage';
import { ReportDetailPage } from '../modules/reports/ReportDetailPage';
import { ReportPreviewPage } from '../modules/reports/ReportPreviewPage';
import { ReportsPage } from '../modules/reports/ReportsPage';

export const router = createBrowserRouter([
  {
    element: createElement(AppShell),
    children: [
      { index: true, element: createElement(Navigate, { to: '/dashboard', replace: true }) },
      { path: '/dashboard', element: createElement(DashboardPage) },
      { path: '/instruments', element: createElement(InstrumentsPage) },
      { path: '/jobs', element: createElement(JobsPage) },
      { path: '/jobs/:jobId', element: createElement(JobDetailPage) },
      { path: '/reports', element: createElement(ReportsPage) },
      { path: '/reports/:reportId', element: createElement(ReportDetailPage) },
      { path: '/reports/:reportId/preview', element: createElement(ReportPreviewPage) },
      { path: '/archive', element: createElement(ArchivePage) },
      { path: '*', element: createElement(Navigate, { to: '/dashboard', replace: true }) },
    ],
  },
]);
