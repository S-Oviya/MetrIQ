import { createElement } from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';

import { AppShell } from '../components/layout/AppShell';
import { ArchivePage } from '../modules/archive/ArchivePage';
import { DashboardPage } from '../modules/dashboard/DashboardPage';
import { ReportsPage } from '../modules/reports/ReportsPage';
import { ReportDetailPage } from '../modules/reports/ReportDetailPage';
import { ReportPreviewPage } from '../modules/reports/ReportPreviewPage';

export const router = createBrowserRouter([
  {
    element: createElement(AppShell),
    children: [
      { index: true, element: createElement(Navigate, { to: '/dashboard', replace: true }) },
      { path: '/dashboard', element: createElement(DashboardPage) },
      { path: '/reports', element: createElement(ReportsPage) },
      { path: '/reports/:reportId', element: createElement(ReportDetailPage) },
      { path: '/reports/:reportId/preview', element: createElement(ReportPreviewPage) },
      { path: '/archive', element: createElement(ArchivePage) },
      { path: '*', element: createElement(Navigate, { to: '/dashboard', replace: true }) },
    ],
  },
]);
