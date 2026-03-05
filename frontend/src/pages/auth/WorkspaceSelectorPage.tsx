import { useState } from 'react';
import { useLocation, useNavigate, Navigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import { BuildingOfficeIcon } from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';
import { authService } from '@/services/authService';
import type { TenantInfo } from '@/types/auth';
import type { ApiErrorResponse } from '@/types/api';

interface LocationState {
  availableTenants?: TenantInfo[];
}

export function WorkspaceSelectorPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((s) => s.login);
  const [serverError, setServerError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);

  const state = location.state as LocationState;
  const tenants = state?.availableTenants;

  // If accessed directly without tenants in state, force them back to login
  if (!tenants || tenants.length === 0) {
    return <Navigate to="/login" replace />;
  }

  const handleSelectTenant = async (tenant: TenantInfo) => {
    if (selectingId) return; // Prevent double-clicks
    
    setServerError(null);
    setSelectingId(tenant.id);

    try {
      // 1. Exchange Identity token for Contextual token
      const ctxRes = await authService.selectTenant({ tenant_id: tenant.id });
      const ctxTokens = ctxRes.data.data;
      
      // 2. Temporarily set token so /me works in the correct context
      useAuthStore.getState().updateTokens({
        access_token: ctxTokens.access_token,
        refresh_token: ctxTokens.refresh_token,
      });

      // 3. Get full user profile (with permissions for this tenant)
      const meRes = await authService.me();
      
      // 4. Persist everything
      login(ctxTokens, meRes.data.data, tenant.code);
      
      // 5. Enter the app
      navigate('/', { replace: true });
    } catch (err) {
      const axiosErr = err as AxiosError<ApiErrorResponse>;
      const detail = axiosErr.response?.data;

      if (detail && 'error' in detail) {
        setServerError(detail.error.message);
      } else if (axiosErr.message) {
        setServerError(axiosErr.message);
      } else {
        setServerError('Failed to select workspace. Please try again.');
      }
      
      setSelectingId(null);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <BuildingOfficeIcon className="mx-auto h-12 w-12 text-primary-600 mb-4" />
          <h1 className="text-3xl font-bold text-gray-900">Welcome Back</h1>
          <p className="mt-2 text-sm text-gray-500">
            Please select a workspace to continue
          </p>
        </div>

        {serverError && (
          <div className="mb-6 rounded-md bg-red-50 p-4 text-sm text-red-700 shadow-sm border border-red-100">
            {serverError}
          </div>
        )}

        <div className="space-y-3">
          {tenants.map((tenant) => (
            <button
              key={tenant.id}
              onClick={() => handleSelectTenant(tenant)}
              disabled={selectingId !== null}
              className={`w-full flex items-center justify-between rounded-xl border border-gray-200 bg-white p-5 text-left shadow-sm transition-all hover:border-primary-500 hover:ring-1 hover:ring-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                selectingId === tenant.id ? 'opacity-75 ring-2 ring-primary-500 border-primary-500' : ''
              } ${selectingId && selectingId !== tenant.id ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div>
                <h3 className="font-semibold text-gray-900">{tenant.name}</h3>
                <p className="text-sm text-gray-500 mt-1">Code: {tenant.code}</p>
              </div>
              <div className="text-primary-600">
                {selectingId === tenant.id ? (
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
            </button>
          ))}
        </div>

        <div className="mt-8 text-center">
          <button 
            onClick={() => {
              useAuthStore.getState().logout();
              navigate('/login');
            }}
            className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors"
          >
            Sign out and try another account
          </button>
        </div>
      </div>
    </div>
  );
}
