import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Modal } from '@/components/ui/Modal';
import type { Tenant } from '@/types/tenant';

const tenantSchema = z.object({
  code: z
    .string()
    .min(3, 'Code must be at least 3 characters')
    .max(32, 'Code must be 32 characters or less')
    .regex(/^[A-Z0-9]+$/, 'Code must be uppercase letters and numbers only'),
  name: z.string().min(1, 'Name is required').max(255, 'Name must be 255 characters or less'),
  address: z.string().optional().or(z.literal('')),
  contact: z.string().optional().or(z.literal('')),
  plan_type: z.string().optional().or(z.literal('')),
});

type TenantFormData = z.infer<typeof tenantSchema>;

interface TenantFormModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: TenantFormData) => Promise<void>;
  tenant?: Tenant | null;
  serverError: string | null;
}

export function TenantFormModal({
  open,
  onClose,
  onSubmit,
  tenant,
  serverError,
}: TenantFormModalProps) {
  const isEdit = !!tenant;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TenantFormData>({
    resolver: zodResolver(tenantSchema),
    defaultValues: {
      code: '',
      name: '',
      address: '',
      contact: '',
      plan_type: '',
    },
  });

  useEffect(() => {
    if (open) {
      reset({
        code: tenant?.code ?? '',
        name: tenant?.name ?? '',
        address: tenant?.address ?? '',
        contact: tenant?.contact ?? '',
        plan_type: tenant?.plan_type ?? '',
      });
    }
  }, [open, tenant, reset]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? 'Edit registry record' : 'Create customer registry record'}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {serverError && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {serverError}
          </div>
        )}

        {!isEdit && (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">
            This creates a registry record only. It does not provision login, tenant schema, admin user, RBAC, inventory, orders, or finance workspace.
          </div>
        )}

        {/* Code */}
        <div>
          <label
            htmlFor="code"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Tenant Code
          </label>
          <input
            id="code"
            type="text"
            placeholder="ACME01"
            disabled={isEdit}
            className="input-field disabled:bg-gray-100 disabled:cursor-not-allowed"
            {...register('code')}
          />
          {errors.code && (
            <p className="mt-1 text-xs text-red-600">{errors.code.message}</p>
          )}
          {isEdit && (
            <p className="mt-1 text-xs text-gray-400">
              Code cannot be changed after creation.
            </p>
          )}
        </div>

        {/* Name */}
        <div>
          <label
            htmlFor="name"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Name
          </label>
          <input
            id="name"
            type="text"
            placeholder="Acme Wholesale Ltd."
            className="input-field"
            {...register('name')}
          />
          {errors.name && (
            <p className="mt-1 text-xs text-red-600">{errors.name.message}</p>
          )}
        </div>

        {/* Address */}
        <div>
          <label
            htmlFor="address"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Address
          </label>
          <input
            id="address"
            type="text"
            placeholder="123 Market St, Nairobi"
            className="input-field"
            {...register('address')}
          />
        </div>

        {/* Contact */}
        <div>
          <label
            htmlFor="contact"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Contact
          </label>
          <input
            id="contact"
            type="text"
            placeholder="+254 700 000 000"
            className="input-field"
            {...register('contact')}
          />
        </div>

        {/* Plan Type */}
        <div>
          <label
            htmlFor="plan_type"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Plan Type
          </label>
          <select id="plan_type" className="input-field" {...register('plan_type')}>
            <option value="">-- Select --</option>
            <option value="free">Free</option>
            <option value="basic">Basic</option>
            <option value="pro">Pro</option>
            <option value="enterprise">Enterprise</option>
          </select>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting
              ? isEdit
                ? 'Saving...'
                : 'Creating...'
              : isEdit
                ? 'Save Changes'
                : 'Create registry record'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
