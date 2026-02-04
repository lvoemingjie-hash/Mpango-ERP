export const UsersPage: React.FC = () => {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Users</h1>
        <p className="mt-1 text-sm text-gray-600">
          Manage users and their roles in your organization
        </p>
      </div>

      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <div className="text-center py-12">
            <h3 className="text-lg font-medium text-gray-900 mb-2">Users Management</h3>
            <p className="text-gray-500 mb-4">
              User management functionality will be implemented here.
            </p>
            <div className="space-y-2 text-sm text-gray-600">
              <p>• View and manage user accounts</p>
              <p>• Assign roles and permissions</p>
              <p>• Create new users</p>
              <p>• Deactivate users</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
