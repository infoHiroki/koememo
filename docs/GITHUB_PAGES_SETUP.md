# Setting Up GitHub Pages for KoeMemo

This guide explains how to set up GitHub Pages to host the KoeMemo documentation website.

## Prerequisites

- A GitHub account
- The KoeMemo repository cloned to your local machine
- Git installed on your computer

## Steps to Enable GitHub Pages

1. **Push the `docs` directory to GitHub**

   Make sure all your HTML, CSS, and image files are committed and pushed to the main branch of your GitHub repository:

   ```bash
   git add docs/
   git commit -m "Add GitHub Pages documentation"
   git push origin main
   ```

2. **Configure GitHub Pages in Repository Settings**

   - Navigate to your GitHub repository in a web browser
   - Click on "Settings" (the gear icon) near the top of the repository page
   - Scroll down to the "GitHub Pages" section
   - Under "Source", select "main branch" (or the branch where your docs are located)
   - In the folder dropdown, select "/docs"
   - Click "Save"

3. **Wait for Deployment**

   - GitHub will begin building your site automatically
   - This process usually takes a minute or two
   - You'll see a green success message with the URL of your published site

4. **Access Your GitHub Pages Site**

   - Your site will be available at: `https://infoHiroki.github.io/koememo/`

## Custom Domain (Optional)

If you want to use a custom domain for your GitHub Pages site:

1. In your repository's Settings > Pages section, enter your custom domain in the "Custom domain" field
2. Click "Save"
3. Follow the DNS configuration instructions provided by GitHub

## Updating Your Site

To update your GitHub Pages site:

1. Make changes to the files in the `docs` directory on your local machine
2. Commit and push those changes to GitHub:

   ```bash
   git add docs/
   git commit -m "Update GitHub Pages site"
   git push origin main
   ```

3. GitHub will automatically rebuild and deploy your site with the changes

## Troubleshooting

- If your site doesn't appear, check the GitHub Pages section in Settings to ensure there are no build errors
- Make sure your repository is public, or you have GitHub Pages enabled for private repositories
- Verify that all image paths and links are correctly set up in your HTML files
- Check that your CSS is properly linked in your HTML files

## Resources

- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Custom Domain Setup Guide](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site)