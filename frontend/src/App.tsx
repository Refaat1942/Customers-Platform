import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./lib/auth";
import { FiltersProvider } from "./lib/filters";
import Layout from "./components/Layout";
import { Notice, Spinner } from "./components/ui";
import Login from "./pages/Login";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Insights = lazy(() => import("./pages/Insights"));
const Customers = lazy(() => import("./pages/Customers"));
const CustomerProfile = lazy(() => import("./pages/CustomerProfile"));
const Area = lazy(() => import("./pages/Area"));
const Products = lazy(() => import("./pages/Products"));
const CustomerBase = lazy(() => import("./pages/CustomerBase"));
const Transactions = lazy(() => import("./pages/Transactions"));
const AIAnalyst = lazy(() => import("./pages/AIAnalyst"));
const Import = lazy(() => import("./pages/Import"));
const UsersPage = lazy(() => import("./pages/Users"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const Audit = lazy(() => import("./pages/Audit"));
const Account = lazy(() => import("./pages/Account"));

function Guard({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useAuth();
  const { t } = useTranslation();
  return can(perm) ? <>{children}</> : <Notice kind="warning">{t("app.noAccess")}</Notice>;
}

/** Send users without dashboard access to the first page they may see. */
function Home() {
  const { can } = useAuth();
  if (can("dashboard")) return <Dashboard />;
  for (const [p, to] of [["customers", "/customers"], ["recommendations", "/recommendations"], ["insights", "/insights"], ["import", "/import"], ["users", "/users"]]) {
    if (can(p)) return <Navigate to={to} replace />;
  }
  return <Navigate to="/account" replace />;
}

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <Spinner />;
  if (!user) return <Routes><Route path="*" element={<Login />} /></Routes>;
  return (
    <FiltersProvider>
      <Suspense fallback={<Spinner />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="insights" element={<Guard perm="insights"><Insights /></Guard>} />
            <Route path="customers" element={<Guard perm="customers"><Customers view="customers" /></Guard>} />
            <Route path="customers/:cid" element={<Guard perm="customers"><CustomerProfile /></Guard>} />
            <Route path="recommendations" element={<Guard perm="recommendations"><Customers view="recommendations" /></Guard>} />
            <Route path="business" element={<Guard perm="business"><Customers view="business" /></Guard>} />
            <Route path="customer-base" element={<Guard perm="customers"><CustomerBase /></Guard>} />
            <Route path="products" element={<Guard perm="business"><Products /></Guard>} />
            <Route path="area" element={<Guard perm="area"><Area /></Guard>} />
            <Route path="transactions" element={<Guard perm="transactions"><Transactions /></Guard>} />
            <Route path="ai" element={<Guard perm="ai"><AIAnalyst /></Guard>} />
            <Route path="import" element={<Guard perm="import"><Import /></Guard>} />
            <Route path="users" element={<Guard perm="users"><UsersPage /></Guard>} />
            <Route path="settings" element={<Guard perm="settings"><SettingsPage /></Guard>} />
            <Route path="audit" element={<Guard perm="audit"><Audit /></Guard>} />
            <Route path="account" element={<Account />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </FiltersProvider>
  );
}
