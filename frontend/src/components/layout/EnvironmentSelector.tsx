import { useEnvironment } from '../../contexts/EnvironmentContext';

export function EnvironmentSelector() {
  const { environments, activeEnvironment, activeRole, setActiveEnvironment, loading, getRoleForEnvironment } = useEnvironment();

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <span className="animate-pulse">Loading...</span>
      </div>
    );
  }

  if (environments.length === 0) {
    return (
      <span className="text-sm text-gray-400">No environments assigned</span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="env-selector" className="text-xs text-gray-500 hidden lg:inline">
        Environment:
      </label>
      <select
        id="env-selector"
        value={activeEnvironment?.id || ''}
        onChange={(e) => {
          const env = environments.find((env) => env.id === e.target.value) || null;
          setActiveEnvironment(env);
        }}
        className="text-sm border border-gray-300 rounded-md px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#00E5FF] focus:border-transparent max-w-[200px] truncate"
      >
        {environments.map((env) => {
          const role = getRoleForEnvironment(env.id);
          const badge = role === 'admin' ? ' [Admin]' : ' [User]';
          return (
            <option key={env.id} value={env.id}>
              {env.name}{badge}
            </option>
          );
        })}
      </select>
      {activeRole && (
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
          activeRole === 'admin'
            ? 'bg-purple-100 text-purple-700'
            : 'bg-blue-100 text-blue-700'
        }`}>
          {activeRole === 'admin' ? 'Admin' : 'User'}
        </span>
      )}
    </div>
  );
}
