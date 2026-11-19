/** Prueba del formulario real en Chromium con transporte API aislado.
 * Desde la raíz: npm install --no-save --prefix <carpeta_temporal> playwright
 * NODE_PATH=<carpeta_temporal>/node_modules node <este_archivo> <salida.json>
 * Instalar Chromium con playwright install chromium si no está disponible.
 * SKILLY_CHROMIUM permite indicar un ejecutable existente. No usa MongoDB.
 */
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const project = path.resolve(__dirname, '../../..');
  const source = fs.readFileSync(path.join(project, 'js/public.js'), 'utf8');
  const functions = source.slice(source.indexOf('function openPublicDialog('), source.indexOf('function requestService('));
  const browser = await chromium.launch({headless: true, ...(process.env.SKILLY_CHROMIUM ? {executablePath: process.env.SKILLY_CHROMIUM} : {})});
  try {
    const page = await browser.newPage();
    await page.setContent('<dialog id="publicDialog"><div id="dialogContent"></div></dialog>');
    await page.addScriptTag({content: `let intentService=null;let apiCalls=[];async function publicApi(...args){apiCalls.push(args);throw Error('Transporte de prueba detenido');}\n${functions}`});
    await page.evaluate(() => authDialog('register'));
    await page.locator('[name=nombre]').fill('Cuenta de prueba');
    await page.locator('[name=correo]').fill('prueba@example.com');
    await page.locator('[name=password]').fill('Qz7!xP2#');
    await page.locator('[name=confirmar]').fill('Otra-clave-2026!');
    await page.locator('[name=mayorEdad]').check();
    await page.locator('[name=aceptoTerminos]').check();
    await page.locator('[type=submit]').click();
    assert.equal(await page.locator('#authError').innerText(), 'Las contraseñas no coinciden.');
    assert.equal(await page.evaluate(() => apiCalls.length), 0);
    const mismatch = {id: 'ALT-02-01', resultado: 'APROBADO', mensaje: await page.locator('#authError').innerText(), llamadasAPI: 0};
    await page.locator('[name=confirmar]').fill('Qz7!xP2#');
    await page.locator('[type=submit]').click();
    await page.waitForFunction(() => apiCalls.length === 1);
    assert.equal(await page.evaluate(() => apiCalls[0][0]), '/api/contratos/politica/');
    const result = {fecha: new Date().toISOString(), alcance: 'Formulario authDialog real; navegador Chromium, API sustituida por transporte controlado. No es una prueba extremo a extremo ni una evaluación humana.', fuente: 'js/public.js', escenarios: [mismatch, {id: 'ALT-02-02', resultado: 'APROBADO', comprobacion: 'Confirmación coincidente permite continuar a la consulta de política; no se crea una cuenta en este ensayo.'}]};
    fs.writeFileSync(process.argv[2] || 'confirmacion_registro.json', JSON.stringify(result, null, 2));
    console.log('2 escenarios de formulario aprobados.');
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode = 1;});
