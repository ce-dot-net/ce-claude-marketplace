/**
 * Email validation utility function for ACE hook testing
 */

/**
 * Validates an email address using regex pattern
 * @param {string} email - The email address to validate
 * @returns {boolean} - True if email is valid, false otherwise
 * @throws {TypeError} - If email is null or undefined
 */
function validateEmail(email) {
  // Error handling for null/undefined inputs
  if (email === null || email === undefined) {
    throw new TypeError('Email cannot be null or undefined');
  }

  // Convert to string if needed
  const emailStr = String(email);

  // Email validation regex pattern
  // Matches: username@domain.tld
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  return emailRegex.test(emailStr);
}

/**
 * Safe email validation that returns false instead of throwing
 * @param {string} email - The email address to validate
 * @returns {boolean} - True if email is valid, false otherwise
 */
function safeValidateEmail(email) {
  try {
    return validateEmail(email);
  } catch (error) {
    return false;
  }
}

/**
 * Validates if an email belongs to a specific domain
 * @param {string} email - The email address to check
 * @param {string} domain - The domain to match (e.g., 'example.com')
 * @returns {boolean} - True if email belongs to the domain, false otherwise
 *
 * @example
 * // Test cases:
 * validateEmailDomain('user@example.com', 'example.com')  // => true
 * validateEmailDomain('user@test.org', 'example.com')     // => false
 * validateEmailDomain('invalid-email', 'example.com')     // => false
 * validateEmailDomain('user@subdomain.example.com', 'example.com')  // => false (exact match)
 */
function validateEmailDomain(email, domain) {
  // First validate the email format
  if (!safeValidateEmail(email)) {
    return false;
  }

  // Extract domain from email
  const emailStr = String(email).toLowerCase();
  const domainStr = String(domain).toLowerCase();

  // Check if email ends with @domain
  return emailStr.endsWith(`@${domainStr}`);
}

/**
 * Validates an array of email addresses and returns only the valid ones
 * @param {string[]} emails - Array of email addresses to validate
 * @returns {string[]} - Array containing only valid email addresses
 *
 * @example
 * const emails = ['user@example.com', 'invalid-email', 'test@domain.org', 'bad@'];
 * const validEmails = validateEmailList(emails);
 * // Returns: ['user@example.com', 'test@domain.org']
 */
function validateEmailList(emails) {
  // Handle edge cases
  if (!Array.isArray(emails)) {
    return [];
  }

  // Filter array to keep only valid emails
  return emails.filter(email => safeValidateEmail(email));
}

module.exports = {
  validateEmail,
  safeValidateEmail,
  validateEmailDomain,
  validateEmailList
};
