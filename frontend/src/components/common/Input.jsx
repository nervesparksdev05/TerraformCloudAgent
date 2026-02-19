import React from 'react';

export const Input = ({ 
  type = 'text',
  placeholder,
  value,
  onChange,
  onKeyDown,
  className = '',
  icon: Icon,
  ...props 
}) => {
  return (
    <div className="relative w-full">
      {Icon && (
        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
          <Icon size={18} />
        </div>
      )}
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        className={`w-full bg-white/5 border border-white/10 rounded-xl p-3 ${Icon ? 'pl-12' : ''} focus:outline-none focus:border-primary-500 transition-all font-medium text-gray-100 placeholder:text-gray-500 ${className}`}
        {...props}
      />
    </div>
  );
};

export default Input;
