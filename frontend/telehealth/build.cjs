const esbuild = require('esbuild');
const fs = require('node:fs/promises');
esbuild.build({entryPoints:['sdk.js'],bundle:true,minify:true,platform:'browser',
  mainFields:['browser','module','main'],format:'iife',globalName:'NuviaVideoSDK',
  legalComments:'linked',outfile:'../../static/telehealth/chime-sdk.js',
  plugins:[{name:'omit-unshipped-source-maps',setup(build){
    build.onLoad({filter:/\.js$/},async args=>({loader:'js',contents:
      (await fs.readFile(args.path,'utf8')).replace(/\/\/[#@]\s*sourceMappingURL=[^\s"'\\]+/g,'')}));
  }}]
}).catch(()=>process.exit(1));
